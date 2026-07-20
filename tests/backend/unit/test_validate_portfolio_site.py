from scripts.validate_portfolio_site import ROOT, PortfolioParser, validate


def _parse(fragment: str) -> PortfolioParser:
    parser = PortfolioParser()
    parser.feed(fragment)
    parser.close()
    return parser


def test_decorative_image_may_have_empty_alt_text():
    parser = _parse('<img src="mark.svg" alt="">')

    assert parser.images_missing_alt == []


def test_image_without_alt_attribute_is_reported():
    parser = _parse('<img src="product.png">')

    assert parser.images_missing_alt == [1]


def test_portfolio_media_preserves_its_intrinsic_ratio():
    errors = validate()

    assert errors == []

    css = (ROOT / "docs" / "site" / "styles.css").read_text(encoding="utf-8")
    for selector in (".product-window img", ".feature-image img"):
        declarations = css.split(f"{selector} {{", maxsplit=1)[1].split("}", maxsplit=1)[0]
        assert "height: auto;" in declarations
        assert "object-fit: contain;" in declarations


def test_portfolio_keeps_one_real_product_demo():
    parser = _parse((ROOT / "docs" / "index.html").read_text(encoding="utf-8"))

    assert parser.video_count == 1
    assert any(
        attribute == "src" and reference == "assets/careeros-demo.webm"
        for attribute, reference, _line in parser.references
    )


def test_portfolio_declares_strict_browser_policies():
    parser = _parse((ROOT / "docs" / "index.html").read_text(encoding="utf-8"))

    assert parser.referrer_policies == ["no-referrer"]
    assert len(parser.csp_policies) == 1
    policy = parser.csp_policies[0]
    assert "default-src 'none'" in policy
    assert "object-src 'none'" in policy
    assert "base-uri 'none'" in policy
    assert "'unsafe-inline'" not in policy
    assert "'unsafe-eval'" not in policy
