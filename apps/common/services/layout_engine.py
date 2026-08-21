import os
import pathlib

class PrintableFrameBuilder:
    @staticmethod
    def build_frame(org, prefs):
        """
        Builds a deterministic, scalable layout frame for rendering printable documents.

        LETTERHEAD MODE:
            - Full-bleed background image covers the sheet when print_on_letterhead is True
              and a valid uploaded letterhead file exists.
            - Header/footer offsets control content top/bottom margins.

        STANDARD MODE:
            - Normal page margins apply. No background image.

        Returns:
            dict: Layout frame parameters injected into the template context.
        """
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
        has_lh = False
        bg_url = None
        top_offset = 30
        bottom_offset = 25

        if print_on_lh and org:
            lh_file = getattr(org, "letterhead", None)
            if lh_file and hasattr(lh_file, "path"):
                try:
                    if os.path.exists(lh_file.path):
                        has_lh = True
                        bg_url = pathlib.Path(lh_file.path).as_uri()
                        header_offset = None
                        footer_offset = None
                        if isinstance(prefs, dict):
                            header_offset = prefs.get("letterhead_header_offset") or prefs.get("header_offset")
                            footer_offset = prefs.get("letterhead_footer_offset") or prefs.get("footer_offset")
                        if header_offset is None:
                            header_offset = getattr(org, "letterhead_header_offset", 30)
                        if footer_offset is None:
                            footer_offset = getattr(org, "letterhead_footer_offset", 25)

                        top_offset = header_offset if header_offset is not None else 30
                        bottom_offset = footer_offset if footer_offset is not None else 25
                except Exception:
                    has_lh = False

        if has_lh and bg_url:
            return {
                "has_letterhead_background": True,
                "background_image_url": bg_url,
                "paper_size": paper_size,
                "orientation": orientation,
                "margin_top": "0",
                "margin_bottom": "0",
                "margin_left": "0",
                "margin_right": "0",
                "body_padding_top": f"{top_offset}mm",
                "body_padding_bottom": f"{bottom_offset}mm",
                "body_padding_left": "15mm",
                "body_padding_right": "15mm",
                "letterhead_mode": True,
            }

        # ── STANDARD MODE ────────────────────────────────────────────────────────
        return {
            "has_letterhead_background": False,
            "background_image_url": "",
            "paper_size": paper_size,
            "orientation": orientation,
            "margin_top": base_margin,
            "margin_bottom": base_margin,
            "margin_left": base_margin,
            "margin_right": base_margin,
            "body_padding_top": "0",
            "body_padding_bottom": "0",
            "body_padding_left": "0",
            "body_padding_right": "0",
            "letterhead_mode": False,
        }
