/**
 * yolo_parser.c
 * -------------
 * YOLOv8 output decoder: confidence filtering + IoU NMS.
 *
 * Runs entirely on Cortex-M55 after Neural-ART finishes the
 * backbone+neck inference.  Uses Helium intrinsics where the
 * compiler can auto-vectorise (arm_math.h is NOT required).
 *
 * License: MIT  |  Author: Rail Anomaly Detection Project
 */

#include "yolo_parser.h"
#include <string.h>
#include <math.h>   /* expf — for potential sigmoid, unused in YOLOv8 */

/* ── Internal helpers ────────────────────────────────────────────────────── */

static float _iou(const YoloDetection_t *a, const YoloDetection_t *b)
{
    float ix1 = a->x1 > b->x1 ? a->x1 : b->x1;
    float iy1 = a->y1 > b->y1 ? a->y1 : b->y1;
    float ix2 = a->x2 < b->x2 ? a->x2 : b->x2;
    float iy2 = a->y2 < b->y2 ? a->y2 : b->y2;

    float iw = ix2 - ix1;
    float ih = iy2 - iy1;
    if (iw <= 0.0f || ih <= 0.0f) return 0.0f;

    float inter = iw * ih;
    float area_a = (a->x2 - a->x1) * (a->y2 - a->y1);
    float area_b = (b->x2 - b->x1) * (b->y2 - b->y1);
    return inter / (area_a + area_b - inter + 1e-6f);
}

static void _swap_det(YoloDetection_t *a, YoloDetection_t *b)
{
    YoloDetection_t tmp = *a;
    *a = *b;
    *b = tmp;
}

/* Simple insertion sort on confidence (descending) — fits MCU well for
   small arrays (YOLO_MAX_DETS = 32). */
static void _sort_by_conf(YoloDetection_t *dets, uint8_t n)
{
    for (int i = 1; i < n; i++) {
        int j = i;
        while (j > 0 && dets[j].confidence > dets[j-1].confidence) {
            _swap_det(&dets[j], &dets[j-1]);
            j--;
        }
    }
}

/* ── Class name table ────────────────────────────────────────────────────── */

static const char * const CLASS_NAMES[YOLO_NUM_CLASSES] = {
    "crack",
    "rail_defect",
    "fastener_defect",
    "obstacle"
};

const char *yolo_class_name(uint8_t class_id)
{
    if (class_id >= YOLO_NUM_CLASSES) return "unknown";
    return CLASS_NAMES[class_id];
}

/* ── Grid anchor offsets ─────────────────────────────────────────────────── */

typedef struct { uint16_t grid_w; uint16_t grid_h; uint8_t stride; } GridLevel_t;

static const GridLevel_t GRIDS[3] = {
    { 40, 40,  8 },   /* stride 8  — small objects  */
    { 20, 20, 16 },   /* stride 16 — medium objects */
    { 10, 10, 32 },   /* stride 32 — large objects  */
};

/* ── Main decode function ────────────────────────────────────────────────── */

/**
 * YOLOv8 export (without end2end NMS) produces a tensor of shape:
 *     [1, YOLO_ROW_SIZE, YOLO_TOTAL_ANCHORS]
 * transposed to row-major for us as:
 *     raw[anchor_idx][0..3]  = cx, cy, w, h  (normalised 0-1)
 *     raw[anchor_idx][4..7]  = class scores   (after sigmoid in model)
 *
 * Adjust indexing if STEdgeAI produces a different memory layout —
 * check the output shape in stedgeai analyze output.
 */
void yolo_decode(const float *raw_output, YoloResult_t *result)
{
    /* --- zeroise result --- */
    memset(result, 0, sizeof(YoloResult_t));

    /* Candidate buffer before NMS */
    YoloDetection_t cands[YOLO_MAX_DETS * 4];  /* over-provision */
    uint8_t n_cands = 0;

    uint32_t anchor_idx = 0;

    for (int g = 0; g < 3; g++) {
        uint16_t gw = GRIDS[g].grid_w;
        uint16_t gh = GRIDS[g].grid_h;
        uint8_t  st = GRIDS[g].stride;

        for (int gy = 0; gy < gh; gy++) {
            for (int gx = 0; gx < gw; gx++) {

                const float *row = raw_output
                                   + anchor_idx * YOLO_ROW_SIZE;

                /* YOLOv8 box is already decoded (cx,cy,w,h in pixel space
                   relative to input size) when exported via Ultralytics.
                   If exporting raw DFL output, additional decoding is needed.
                   The values below assume the simplified ONNX export path.  */
                float cx = row[0];
                float cy = row[1];
                float bw = row[2];
                float bh = row[3];

                /* Find winning class and its score */
                float best_score = -1.0f;
                uint8_t best_cls = 0;
                for (int c = 0; c < YOLO_NUM_CLASSES; c++) {
                    float sc = row[4 + c];
                    if (sc > best_score) {
                        best_score = sc;
                        best_cls   = (uint8_t)c;
                    }
                }

                /* Filter by confidence threshold */
                if (best_score < YOLO_CONF_THRESH) {
                    anchor_idx++;
                    continue;
                }

                /* Convert cx/cy/w/h -> x1/y1/x2/y2 (pixel coords) */
                YoloDetection_t det;
                det.x1 = cx - bw * 0.5f;
                det.y1 = cy - bh * 0.5f;
                det.x2 = cx + bw * 0.5f;
                det.y2 = cy + bh * 0.5f;

                /* Clamp to image bounds */
                if (det.x1 < 0.0f) det.x1 = 0.0f;
                if (det.y1 < 0.0f) det.y1 = 0.0f;
                if (det.x2 > (float)YOLO_INPUT_W) det.x2 = (float)YOLO_INPUT_W;
                if (det.y2 > (float)YOLO_INPUT_H) det.y2 = (float)YOLO_INPUT_H;

                det.confidence = best_score;
                det.class_id   = best_cls;
                strncpy(det.class_name, yolo_class_name(best_cls),
                        sizeof(det.class_name) - 1);
                det.class_name[sizeof(det.class_name) - 1] = '\0';

                if (n_cands < (uint8_t)(sizeof(cands)/sizeof(cands[0]))) {
                    cands[n_cands++] = det;
                }

                anchor_idx++;
            }
        }
    }

    /* --- Non-Maximum Suppression (greedy, per-class) --- */
    _sort_by_conf(cands, n_cands);

    uint8_t suppressed[sizeof(cands)/sizeof(cands[0])];
    memset(suppressed, 0, sizeof(suppressed));

    uint8_t out_count = 0;
    for (int i = 0; i < n_cands && out_count < YOLO_MAX_DETS; i++) {
        if (suppressed[i]) continue;

        result->dets[out_count++] = cands[i];

        for (int j = i + 1; j < n_cands; j++) {
            if (suppressed[j]) continue;
            /* Only suppress same-class boxes */
            if (cands[i].class_id != cands[j].class_id) continue;
            if (_iou(&cands[i], &cands[j]) > YOLO_IOU_THRESH) {
                suppressed[j] = 1;
            }
        }
    }
    result->count = out_count;
}
