"""Tests for branding extraction service."""

from supacrawl.services.branding import BrandingExtractor


class TestBrandingExtractor:
    """Tests for BrandingExtractor."""

    def test_extract_colors_from_css_variables(self):
        """Test colour extraction from CSS custom properties."""
        html = """
        <html>
            <head>
                <style>
                    :root {
                        --primary-color: #FF6B35;
                        --secondary-color: #004E89;
                        --background-color: #1A1A1A;
                        --text-color: #FFFFFF;
                    }
                </style>
            </head>
            <body></body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.colors is not None
        assert branding.colors.primary == "#FF6B35"
        assert branding.colors.secondary == "#004E89"
        assert branding.colors.background == "#1A1A1A"
        assert branding.colors.text_primary == "#FFFFFF"

    def test_extract_fonts_from_css(self):
        """Test font extraction from font-family declarations."""
        html = """
        <html>
            <head>
                <style>
                    body {
                        font-family: "Inter", sans-serif;
                    }
                    h1 {
                        font-family: "Roboto", serif;
                    }
                </style>
            </head>
            <body></body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.fonts is not None
        assert len(branding.fonts) >= 2
        font_families = [f["family"] for f in branding.fonts]
        assert "Inter" in font_families
        assert "Roboto" in font_families

    def test_extract_fonts_from_google_fonts(self):
        """Test font extraction from Google Fonts links."""
        html = """
        <html>
            <head>
                <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
            </head>
            <body></body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.fonts is not None
        assert len(branding.fonts) >= 1
        assert branding.fonts[0]["family"] == "Inter"

    def test_extract_logo_from_img_tag(self):
        """Test logo extraction from img tag."""
        html = """
        <html>
            <body>
                <header>
                    <img class="logo" src="/logo.svg" alt="Logo">
                </header>
            </body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.logo is not None
        assert branding.logo == "https://example.com/logo.svg"

    def test_detect_dark_color_scheme(self):
        """Test dark colour scheme detection."""
        html = """
        <html class="dark">
            <body></body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.color_scheme == "dark"

    def test_detect_light_color_scheme(self):
        """Test light colour scheme detection."""
        html = """
        <html class="light">
            <body></body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.color_scheme == "light"

    def test_extract_typography_font_sizes(self):
        """Test typography font size extraction."""
        html = """
        <html>
            <head>
                <style>
                    h1 { font-size: 48px; }
                    h2 { font-size: 36px; }
                    body { font-size: 16px; }
                </style>
            </head>
            <body></body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.typography is not None
        assert "fontSizes" in branding.typography
        assert branding.typography["fontSizes"]["h1"] == "48px"
        assert branding.typography["fontSizes"]["h2"] == "36px"
        assert branding.typography["fontSizes"]["body"] == "16px"

    def test_extract_spacing_border_radius(self):
        """Test spacing extraction including border-radius."""
        html = """
        <html>
            <head>
                <style>
                    button { border-radius: 8px; }
                    :root {
                        --spacing-unit: 8px;
                    }
                </style>
            </head>
            <body></body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.spacing is not None
        assert branding.spacing["borderRadius"] == "8px"

    def test_extract_brand_images(self):
        """Test brand image URL extraction."""
        html = """
        <html>
            <head>
                <link rel="icon" href="/favicon.ico">
                <meta property="og:image" content="https://example.com/og.png">
            </head>
            <body></body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.images is not None
        assert branding.images["favicon"] == "https://example.com/favicon.ico"
        assert branding.images["ogImage"] == "https://example.com/og.png"

    def test_extract_from_minimal_html(self):
        """Test extraction from minimal HTML without styling."""
        html = "<html><body><p>Plain text</p></body></html>"
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        # Should not crash, just return minimal branding
        assert branding is not None
        assert branding.color_scheme == "light"  # Default

    def test_extract_colors_from_meta_theme(self):
        """Test colour extraction from meta theme-color."""
        html = """
        <html>
            <head>
                <meta name="theme-color" content="#FF6B35">
            </head>
            <body></body>
        </html>
        """
        extractor = BrandingExtractor()
        branding = extractor.extract(html, "https://example.com")

        assert branding.colors is not None
        assert branding.colors.primary == "#FF6B35"
