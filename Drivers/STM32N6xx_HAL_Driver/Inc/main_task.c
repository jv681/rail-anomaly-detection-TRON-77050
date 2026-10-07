/**
 * main_task.c
 * -----------
 * µT-Kernel 3.0 application for railway anomaly detection on STM32N657.
 *
 * Task architecture:
 *   CameraTask    (priority 4) — capture frame, write to shared buffer,
 *                                signal InferenceTask
 *   InferenceTask (priority 5) — preprocess, run Neural-ART, decode YOLO,
 *                                send results to AlertTask via mailbox
 *   AlertTask     (priority 6) — receive detections, log/alert via UART
 *
 * Lower numeric priority = higher scheduling priority in µT-Kernel.
 *
 * STEdgeAI-generated files required (from stedgeai generate output):
 *   network.h / network.c
 *   network_data.h / network_data.c
 *   ai_platform.h
 *
 * License: MIT  |  Author: Rail Anomaly Detection Project
 * Third-party:
 *   - µT-Kernel 3.0  (TRON Forum, BSD-3)
 *   - ST Edge AI Core runtime  (STMicroelectronics, SLA0044)
 *   - YOLOv8n weights (Ultralytics, AGPL-3.0 — see docs/operation_manual.md)
 */

#include <tk/tkernel.h>     /* µT-Kernel 3.0 core API                */
#include <tm/tmonitor.h>    /* tm_printf() — debug UART               */

/* STEdgeAI generated headers — add to include path after code-gen */
#include "network.h"
#include "network_data.h"
#include "ai_platform.h"

/* Application headers */
#include "yolo_parser.h"

/* ── Platform / board specifics ─────────────────────────────────────────── */
/* Adjust these for your camera peripheral and HAL.
   The DK board typically uses a DCMI + DMA pipeline.                       */
extern void Camera_Init(void);
extern void Camera_CaptureFrame(uint8_t *buf, uint32_t w, uint32_t h);
extern void UART_SendStr(const char *str);

/* ── Shared camera frame buffer ─────────────────────────────────────────── */
/* 320×320 RGB888, placed in SRAM.
   Attribute places it in the fast internal SRAM bank.                      */
static uint8_t __attribute__((section(".sram")))
    s_frame_buf[YOLO_INPUT_H * YOLO_INPUT_W * 3];

/* ── Neural-ART (STEdgeAI) runtime handles ──────────────────────────────── */
static ai_handle          s_network = AI_HANDLE_NULL;
static ai_buffer          s_ai_input[AI_NETWORK_IN_NUM];
static ai_buffer          s_ai_output[AI_NETWORK_OUT_NUM];

/* ── Float input tensor (post-normalisation) ────────────────────────────── */
static float __attribute__((section(".sram")))
    s_input_f32[YOLO_INPUT_H * YOLO_INPUT_W * 3];

/* ── Raw NPU output tensor ──────────────────────────────────────────────── */
static float s_output_f32[YOLO_TOTAL_ANCHORS * YOLO_ROW_SIZE];

/* ── Mailbox: InferenceTask -> AlertTask ────────────────────────────────── */
static ID    s_mbx_id   = 0;
static ID    s_sem_frame = 0;   /* signals new frame ready */

/* ── Task IDs ───────────────────────────────────────────────────────────── */
static ID s_camera_tid    = 0;
static ID s_inference_tid = 0;
static ID s_alert_tid     = 0;

/* Mailbox message envelope */
typedef struct {
    T_MSG    hdr;           /* µT-Kernel mailbox header — MUST be first */
    YoloResult_t result;
} DetectionMsg_t;

/* Pool of pre-allocated message envelopes (avoid malloc on MCU) */
#define MSG_POOL_SIZE 4
static DetectionMsg_t s_msg_pool[MSG_POOL_SIZE];
static uint8_t        s_msg_pool_idx = 0;

static DetectionMsg_t *alloc_msg(void)
{
    /* Circular pool — safe because AlertTask consumes faster than produced */
    DetectionMsg_t *m = &s_msg_pool[s_msg_pool_idx];
    s_msg_pool_idx = (s_msg_pool_idx + 1) % MSG_POOL_SIZE;
    return m;
}

/* ══════════════════════════════════════════════════════════════════════════
 * CameraTask — captures one frame per inference cycle
 * ══════════════════════════════════════════════════════════════════════════ */
static void CameraTask(INT stacd, void *exinf)
{
    (void)stacd; (void)exinf;

    tm_printf((UB *)"[Camera] Task started\n");

    for (;;) {
        /* Block until InferenceTask is ready for a new frame */
        tk_wai_sem(s_sem_frame, 1, TMO_FEVR);

        /* Capture 320×320 RGB frame via DCMI/DMA */
        Camera_CaptureFrame(s_frame_buf, YOLO_INPUT_W, YOLO_INPUT_H);

        /* Preprocess: uint8 RGB -> float32 normalised [0.0, 1.0]
           Loop is auto-vectorised by GCC with -mfpu=fpv5-d16            */
        const uint32_t n_pixels = YOLO_INPUT_W * YOLO_INPUT_H * 3;
        for (uint32_t i = 0; i < n_pixels; i++) {
            s_input_f32[i] = (float)s_frame_buf[i] / 255.0f;
        }

        /* Signal InferenceTask that s_input_f32 is ready */
        tk_sig_sem(s_sem_frame, 1);

        /* Yield to higher-priority tasks */
        tk_dly_tsk(1);
    }
}

/* ══════════════════════════════════════════════════════════════════════════
 * InferenceTask — runs Neural-ART and decodes output
 * ══════════════════════════════════════════════════════════════════════════ */
static void InferenceTask(INT stacd, void *exinf)
{
    (void)stacd; (void)exinf;

    /* -- Initialise Neural-ART network (once at boot) ------------------- */
    ai_error ai_err;
    s_network = ai_network_create(ai_network_data_weights_get(), &ai_err);
    if (s_network == AI_HANDLE_NULL) {
        tm_printf((UB *)"[Inference] FATAL: ai_network_create failed %d\n",
                  ai_err.code);
        tk_ext_tsk();
    }

    /* Wire input/output buffers to STEdgeAI descriptors */
    ai_network_inputs_get(s_network, s_ai_input);
    ai_network_outputs_get(s_network, s_ai_output);

    s_ai_input[0].data  = AI_BUFFER_DATA(NULL, s_input_f32);
    s_ai_output[0].data = AI_BUFFER_DATA(NULL, s_output_f32);

    tm_printf((UB *)"[Inference] Neural-ART initialised OK\n");

    /* Trigger first camera capture */
    tk_sig_sem(s_sem_frame, 1);

    for (;;) {
        /* Wait for CameraTask to finish preprocessing */
        tk_wai_sem(s_sem_frame, 1, TMO_FEVR);

        /* -- Run Neural-ART (backbone+neck on NPU, head on M55) --------- */
        ai_i32 n_batch = ai_network_run(s_network, s_ai_input, s_ai_output);
        if (n_batch != 1) {
            tm_printf((UB *)"[Inference] WARN: ai_network_run returned %d\n",
                      (int)n_batch);
        }

        /* -- Decode YOLO output on Cortex-M55 --------------------------- */
        DetectionMsg_t *msg = alloc_msg();
        yolo_decode(s_output_f32, &msg->result);

        /* Send detections to AlertTask (non-blocking) */
        if (msg->result.count > 0) {
            tk_snd_mbx(s_mbx_id, (T_MSG *)msg);
        }

        /* Immediately request the next frame */
        tk_sig_sem(s_sem_frame, 1);
    }
}

/* ══════════════════════════════════════════════════════════════════════════
 * AlertTask — logs detections and triggers board alerts
 * ══════════════════════════════════════════════════════════════════════════ */
static void AlertTask(INT stacd, void *exinf)
{
    (void)stacd; (void)exinf;

    char msg_buf[128];
    tm_printf((UB *)"[Alert] Task started\n");

    for (;;) {
        DetectionMsg_t *msg = NULL;
        ER err = tk_rcv_mbx(s_mbx_id, (T_MSG **)&msg, TMO_FEVR);
        if (err != E_OK || msg == NULL) continue;

        /* Log each detection over UART */
        for (int i = 0; i < msg->result.count; i++) {
            YoloDetection_t *d = &msg->result.dets[i];
            snprintf(msg_buf, sizeof(msg_buf),
                     "{\"class\":\"%s\",\"conf\":%.2f,"
                     "\"x1\":%.1f,\"y1\":%.1f,\"x2\":%.1f,\"y2\":%.1f}\r\n",
                     d->class_name, d->confidence,
                     d->x1, d->y1, d->x2, d->y2);
            UART_SendStr(msg_buf);

            /* Board-level alert: LED or buzzer per class */
            switch (d->class_id) {
                case CLASS_CRACK:
                case CLASS_RAIL_DEFECT:
                    /* Critical — red LED + buzzer */
                    /* HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET); */
                    break;
                case CLASS_FASTENER:
                    /* Warning — yellow LED */
                    break;
                case CLASS_OBSTACLE:
                    /* Immediate — all LEDs + buzzer */
                    break;
                default: break;
            }
        }
    }
}

/* ══════════════════════════════════════════════════════════════════════════
 * usermain() — µT-Kernel 3.0 application entry point
 *              Called after the kernel boots.  Do NOT rename.
 * ══════════════════════════════════════════════════════════════════════════ */
EXPORT INT usermain(void)
{
    ER err;

    tm_printf((UB *)"=== Rail Anomaly Detection v1.0 ===\n");
    tm_printf((UB *)"    YOLOv8n / Neural-ART / uT-Kernel 3.0\n\n");

    /* -- Create mailbox -------------------------------------------------- */
    T_CMBX cmbx = { .mbxatr = TA_TFIFO | TA_MFIFO };
    s_mbx_id = tk_cre_mbx(&cmbx);
    if (s_mbx_id < E_OK) {
        tm_printf((UB *)"FATAL: tk_cre_mbx failed %d\n", s_mbx_id);
        return s_mbx_id;
    }

    /* -- Create semaphore (frame-ready signal) --------------------------- */
    T_CSEM csem = { .sematr = TA_TFIFO, .isemcnt = 0, .maxsem = 1 };
    s_sem_frame = tk_cre_sem(&csem);
    if (s_sem_frame < E_OK) {
        tm_printf((UB *)"FATAL: tk_cre_sem failed %d\n", s_sem_frame);
        return s_sem_frame;
    }

    /* -- Create tasks ---------------------------------------------------- */
    T_CTSK ctsk_cam = {
        .tskatr  = TA_HLNG | TA_RNG0,
        .task    = CameraTask,
        .itskpri = 4,
        .stksz   = 512,
    };
    s_camera_tid = tk_cre_tsk(&ctsk_cam);

    T_CTSK ctsk_inf = {
        .tskatr  = TA_HLNG | TA_RNG0,
        .task    = InferenceTask,
        .itskpri = 5,
        .stksz   = 1024,
    };
    s_inference_tid = tk_cre_tsk(&ctsk_inf);

    T_CTSK ctsk_alt = {
        .tskatr  = TA_HLNG | TA_RNG0,
        .task    = AlertTask,
        .itskpri = 6,
        .stksz   = 512,
    };
    s_alert_tid = tk_cre_tsk(&ctsk_alt);

    /* -- Initialise camera peripheral ----------------------------------- */
    Camera_Init();

    /* -- Start all tasks ------------------------------------------------ */
    err  = tk_sta_tsk(s_alert_tid,    0);
    err |= tk_sta_tsk(s_inference_tid, 0);
    err |= tk_sta_tsk(s_camera_tid,   0);

    if (err != E_OK) {
        tm_printf((UB *)"FATAL: tk_sta_tsk failed %d\n", err);
        return err;
    }

    tm_printf((UB *)"All tasks started. Entering idle loop.\n");

    /* µT-Kernel requires usermain to block (not return) */
    tk_slp_tsk(TMO_FEVR);
    return 0;
}
