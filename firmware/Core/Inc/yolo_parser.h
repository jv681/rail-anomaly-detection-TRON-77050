/**
 * yolo_parser.h
 * -------------
 * Lightweight YOLOv8 output decoder for µT-Kernel 3.0 / STM32N657.
 *
 * Parses the raw output tensors produced by ai_network_run() and
 * returns decoded bounding boxes with class labels and confidences.
 *
 * No dynamic allocation — all buffers are fixed-size and caller-owned.
 *
 * License: MIT  |  Author: Rail Anomaly Detection Project
 */

#ifndef YOLO_PARSER_H
#define YOLO_PARSER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── Configuration ──────────────────────────────────────────────────────── */

/** Input image dimensions used during export. Change if you use 256px. */
#define YOLO_INPUT_W        320
#define YOLO_INPUT_H        320

/** Number of detection classes. */
#define YOLO_NUM_CLASSES    4

/** Class labels (index must match training data.yaml order). */
#define CLASS_CRACK         0
#define CLASS_RAIL_DEFECT   1
#define CLASS_FASTENER      2
#define CLASS_OBSTACLE      3

/** Maximum detections after NMS (memory budget). */
#define YOLO_MAX_DETS       32

/** Confidence threshold — raise to reduce false positives on MCU. */
#define YOLO_CONF_THRESH    0.40f

/** IoU threshold for NMS. */
#define YOLO_IOU_THRESH     0.45f

/** YOLOv8n output: 3 strides x (4 + NUM_CLASSES) per anchor.
 *  Stride 8  → grid 40×40 = 1600 anchors
 *  Stride 16 → grid 20×20 =  400 anchors
 *  Stride 32 → grid 10×10 =  100 anchors
 *  Total raw predictions: 2100 × (4 + 4) = 2100 rows                      */
#define YOLO_TOTAL_ANCHORS  2100   /* (40*40) + (20*20) + (10*10) */
#define YOLO_ROW_SIZE       (4 + YOLO_NUM_CLASSES)

/* ── Output structures ───────────────────────────────────────────────────── */

/**
 * A single decoded detection (absolute pixel coordinates).
 * Coordinates are in [0, YOLO_INPUT_W/H] range.
 */
typedef struct {
    float    x1, y1;          /**< Top-left corner */
    float    x2, y2;          /**< Bottom-right corner */
    float    confidence;      /**< Class confidence score */
    uint8_t  class_id;        /**< Winning class index (0-3) */
    char     class_name[24];  /**< Human-readable label */
} YoloDetection_t;

/**
 * Container returned by yolo_decode().
 */
typedef struct {
    YoloDetection_t dets[YOLO_MAX_DETS];
    uint8_t         count;      /**< Number of valid detections */
} YoloResult_t;

/* ── API ─────────────────────────────────────────────────────────────────── */

/**
 * yolo_decode() — decode raw STEdgeAI output into YoloResult_t.
 *
 * @param raw_output   Pointer to the flat float32 output tensor from
 *                     ai_network_run().  Shape: [YOLO_TOTAL_ANCHORS][YOLO_ROW_SIZE]
 *                     laid out in row-major order.
 * @param result       Caller-allocated result buffer.  Zeroed on entry.
 *
 * Call from InferenceTask after ai_network_run() returns.
 * This function runs entirely on Cortex-M55 (no NPU).
 */
void yolo_decode(const float *raw_output, YoloResult_t *result);

/**
 * yolo_class_name() — return a constant string for a class id.
 * Returns "unknown" for out-of-range ids.
 */
const char *yolo_class_name(uint8_t class_id);

#ifdef __cplusplus
}
#endif

#endif /* YOLO_PARSER_H */
