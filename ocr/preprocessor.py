"""
ImagePreprocessor
-----------------
Prepares a PDF page image for OCR using OpenCV.

Pipeline (in order):
  1. Render — fitz.Page → high-DPI pixmap → numpy BGR array
  2. Grayscale — reduce to single channel
  3. Denoise — remove scan noise without blurring text strokes
  4. Deskew — correct slight page rotation (up to ±10°)
  5. Binarize — Otsu adaptive threshold → clean black-on-white

Each step is a standalone method and can be called independently
for debugging or testing.
"""

import logging
from typing import Optional

import cv2
import fitz
import numpy as np

logger = logging.getLogger(__name__)

# Render DPI: 300 is the standard OCR minimum.
# Higher = better accuracy, slower processing, more memory.
RENDER_DPI = 300


class ImagePreprocessor:
    """
    Converts a fitz.Page into a preprocessed numpy image for OCR.

    Parameters
    ----------
    dpi           : Render resolution. Default 300.
    denoise       : Whether to apply denoising. Default True.
    deskew        : Whether to correct page rotation. Default True.
    binarize      : Whether to apply Otsu binarization. Default True.
    max_skew_deg  : Maximum skew angle to correct. Beyond this the page
                    is likely intentionally rotated and we skip correction.
                    Default 10.0 degrees.
    """

    def __init__(
        self,
        dpi:          int   = RENDER_DPI,
        denoise:      bool  = True,
        deskew:       bool  = True,
        binarize:     bool  = True,
        max_skew_deg: float = 10.0,
    ) -> None:
        self.dpi          = dpi
        self.denoise      = denoise
        self.deskew       = deskew
        self.binarize     = binarize
        self.max_skew_deg = max_skew_deg

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prepare(self, page: fitz.Page) -> np.ndarray:
        """
        Full preprocessing pipeline.

        Parameters
        ----------
        page : fitz.Page

        Returns
        -------
        np.ndarray
            Preprocessed grayscale or binary image, dtype uint8.
        """
        img = self.render(page)
        img = self.to_grayscale(img)

        if self.denoise:
            img = self.remove_noise(img)
        if self.deskew:
            img = self.correct_skew(img)
        if self.binarize:
            img = self.binarize_image(img)

        return img

    # ------------------------------------------------------------------
    # Individual steps
    # ------------------------------------------------------------------

    def render(self, page: fitz.Page) -> np.ndarray:
        """
        Render a PDF page to a BGR numpy array.

        Uses PyMuPDF's pixmap renderer at the configured DPI.
        """
        scale = self.dpi / 72.0  # 72 is PDF's native "points per inch"
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)

        # pix.samples is raw RGB bytes — convert to numpy then to BGR for OpenCV
        img = np.frombuffer(pix.samples, dtype=np.uint8)
        img = img.reshape(pix.height, pix.width, 3)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        logger.debug(
            "Rendered page %d at %d DPI → %dx%d px",
            page.number + 1, self.dpi, pix.width, pix.height,
        )
        return img

    def to_grayscale(self, img: np.ndarray) -> np.ndarray:
        """Convert BGR image to grayscale."""
        if len(img.shape) == 2:
            return img  # already grayscale
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def remove_noise(self, img: np.ndarray) -> np.ndarray:
        """
        Apply fast non-local means denoising.

        h=10 is a good balance between noise removal and text preservation.
        Higher h values blur thin strokes (bad for Nastaliq ligatures).
        """
        try:
            return cv2.fastNlMeansDenoising(img, h=10, templateWindowSize=7, searchWindowSize=21)
        except Exception as exc:
            logger.warning("Denoising failed: %s — skipping.", exc)
            return img

    def correct_skew(self, img: np.ndarray) -> np.ndarray:
        """
        Detect and correct page skew using image moments.

        Algorithm:
          1. Threshold the image to get foreground pixels.
          2. Compute image moments to find the dominant text angle.
          3. If the angle is within max_skew_deg, rotate to correct.
          4. If the angle is too large, assume intentional rotation — skip.
        """
        try:
            # Invert so text is white (foreground) on black
            _, thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) < 100:
                # Not enough foreground pixels to compute a reliable angle
                return img

            angle = cv2.minAreaRect(coords)[-1]

            # minAreaRect returns angles in [-90, 0); convert to [-45, 45)
            if angle < -45:
                angle = 90 + angle

            if abs(angle) > self.max_skew_deg:
                logger.debug(
                    "Skew angle %.1f° exceeds max %.1f° — skipping correction.",
                    angle, self.max_skew_deg,
                )
                return img

            logger.debug("Correcting skew: %.2f°", angle)
            h, w = img.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(
                img, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            return rotated

        except Exception as exc:
            logger.warning("Skew correction failed: %s — skipping.", exc)
            return img

    def binarize_image(self, img: np.ndarray) -> np.ndarray:
        """
        Apply Otsu's binarization to produce a clean black-on-white image.

        Otsu automatically selects the optimal threshold from the image
        histogram — no manual tuning needed across different scan qualities.
        """
        try:
            _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return binary
        except Exception as exc:
            logger.warning("Binarization failed: %s — skipping.", exc)
            return img