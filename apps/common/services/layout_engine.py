"""
apps/common/services/layout_engine.py
"""

class PrintableFrameBuilder:
    @staticmethod
    def build_frame(org, prefs):
        """
        Builds a deterministic, scalable layout frame for rendering printable documents.

        LETTERHEAD MODE:
            - The page has NO margins (full-bleed background image covers the sheet).
            - The <body> acts as the Printable Content Frame with padding equal to the
              header/footer offsets the user configured. This is exactly how Microsoft
              Word prints onto company stationery.

        STANDARD MODE:
            - Normal page margins apply. No background image.

        Returns:
            dict: Layout frame parameters injected into the template context.
        """
        # Read preferences
        if isinstance(prefs, dict):
            paper_size      = prefs.get("paper_size", "A4")
            orientation     = prefs.get("orientation", "Portrait")
            margins_pref    = prefs.get("margins", "Normal")
            print_on_lh     = prefs.get("print_on_letterhead", False)
        else:
            paper_size      = getattr(prefs, "paper_size", "A4")
            orientation     = getattr(prefs, "orientation", "Portrait")
            margins_pref    = getattr(prefs, "margins", "Normal")
            print_on_lh     = getattr(prefs, "print_on_letterhead", False)

        # Base page-margin from preferences (used in standard mode only)
        if margins_pref == "Narrow":
            base_margin = "10mm"
        elif margins_pref == "Wide":
            base_margin = "25mm"
        else:
            base_margin = "15mm"

        # ── LETTERHEAD MODE ──────────────────────────────────────────────────────
        if print_on_lh and org and getattr(org, "letterhead", None):
            top_offset    = getattr(org, "letterhead_header_offset", 30)
            bottom_offset = getattr(org, "letterhead_footer_offset", 25)

            return {
                # Page is full-bleed: no margins, background covers entire sheet
                "has_letterhead_background": True,
                "background_image_url": f"file://{org.letterhead.path}",
                "paper_size":    paper_size,
                "orientation":   orientation,
                # Page margins are zero — the full-bleed background covers the sheet
                "margin_top":    "0",
                "margin_bottom": "0",
                "margin_left":   "0",
                "margin_right":  "0",
                # The master table spacers will use these padding values to push content down
                "body_padding_top":    f"{top_offset}mm",
                "body_padding_bottom": f"{bottom_offset}mm",
                "body_padding_left":   "15mm",
                "body_padding_right":  "15mm",
                "letterhead_mode":     True,
            }

        # ── STANDARD MODE ────────────────────────────────────────────────────────
        return {
            "has_letterhead_background": False,
            "background_image_url":      None,
            "paper_size":    paper_size,
            "orientation":   orientation,
            "margin_top":    base_margin,
            "margin_bottom": base_margin,
            "margin_left":   base_margin,
            "margin_right":  base_margin,
            # No body padding override in standard mode
            "body_padding_top":    None,
            "body_padding_bottom": None,
            "body_padding_left":   None,
            "body_padding_right":  None,
            "letterhead_mode":     False,
        }
