def make_base_lead(
    *,
    raw_html: str,
    text_content: str,
    source_url: str = "https://example-hvac.com",
    page_title: str = "Example HVAC",
    phone_number: str = "503-555-1234",
    address: str = "123 Main St, Portland, OR",
    rating_count: int = 10,
    anchor_hrefs: list | None = None,
    robots_exists: bool = True,
    sitemap_exists: bool = True,
) -> dict:
    return {
        "raw_html": raw_html,
        "text_content": text_content,
        "page_title": page_title,
        "anchor_hrefs": anchor_hrefs or [],
        "robots_txt": {
            "path": "/robots.txt",
            "http_status": 200 if robots_exists else 404,
            "exists": robots_exists,
            "content_type": "text/plain",
            "body": "User-agent: *",
        },
        "sitemap_xml": {
            "path": "/sitemap.xml",
            "http_status": 200 if sitemap_exists else 404,
            "exists": sitemap_exists,
            "content_type": "application/xml",
            "body": "<urlset></urlset>",
        },
        "source_url": source_url,
        "phone_number": phone_number,
        "address": address,
        "rating_count": rating_count,
    }


def weak_website_hvac_lead() -> dict:
    raw_html = """
    <html>
      <head>
        <title>AAA Heating and Cooling</title>
      </head>
      <body>
        <h1>AAA Heating and Cooling</h1>
        <p>Residential HVAC repair and installation in Portland.</p>
        <p>Call us today for heating and cooling service.</p>
        <form action="/contact">
          <input type="text" name="name" />
        </form>
        <a href="/contact">Contact</a>
      </body>
    </html>
    """
    text_content = (
        "AAA Heating and Cooling residential HVAC repair and installation in Portland. "
        "Call us today for heating and cooling service. Furnace repair AC repair heat pump service."
    )
    return make_base_lead(
        raw_html=raw_html,
        text_content=text_content,
        source_url="https://aaaheatingandcoolinginc.com/",
    )


def voice_ai_candidate_lead() -> dict:
    raw_html = """
    <html>
      <head>
        <title>Fast Response Plumbing</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        <h1>Fast Response Plumbing</h1>
        <p>Emergency plumbing service in Portland.</p>
        <p>Call now for same-day service.</p>
        <a href="tel:5035559999">Call Now</a>
      </body>
    </html>
    """
    text_content = (
        "Fast Response Plumbing emergency plumbing service in Portland. "
        "Call now for same-day service. Emergency service available."
    )
    return make_base_lead(
        raw_html=raw_html,
        text_content=text_content,
        source_url="https://fastresponseplumbing.com/",
        phone_number="503-555-9999",
    )


def smma_candidate_without_socials() -> dict:
    raw_html = """
    <html>
      <head>
        <title>Rose City Auto Detail</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        <h1>Rose City Auto Detail</h1>
        <p>Auto detailing and ceramic coating in Portland.</p>
        <p>Book an appointment today.</p>
        <a href="/contact">Contact</a>
      </body>
    </html>
    """
    text_content = (
        "Rose City Auto Detail auto detailing and ceramic coating in Portland. "
        "Book an appointment today."
    )
    return make_base_lead(
        raw_html=raw_html,
        text_content=text_content,
        source_url="https://rosecityautodetail.com/",
        anchor_hrefs=[
            {"url": "https://rosecityautodetail.com/contact", "is_internal": True, "label": "Contact"},
        ],
    )


def directory_like_lead() -> dict:
    raw_html = """
    <html>
      <head><title>Yelp Listing</title></head>
      <body>
        <h1>Best HVAC in Portland</h1>
        <p>Find the top-rated HVAC companies near you.</p>
      </body>
    </html>
    """
    text_content = "Find the top-rated HVAC companies near you in Portland."
    return make_base_lead(
        raw_html=raw_html,
        text_content=text_content,
        source_url="https://www.yelp.com/biz/example",
        phone_number="",
        address="",
        rating_count=0,
    )


def modern_business_lead() -> dict:
    raw_html = """
    <html>
      <head>
        <title>Northwest Comfort Solutions</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        <h1>Northwest Comfort Solutions</h1>
        <p>Professional HVAC installation, repair, and maintenance in Portland.</p>
        <p>Request a quote today.</p>
        <form action="/quote">
          <input type="text" name="name" />
          <input type="email" name="email" />
        </form>
        <a href="/contact">Contact</a>
        <a href="/privacy-policy">Privacy Policy</a>
      </body>
    </html>
    """
    text_content = (
        "Northwest Comfort Solutions professional HVAC installation repair and maintenance "
        "in Portland. Request a quote today. Contact us for service."
    )
    return make_base_lead(
        raw_html=raw_html,
        text_content=text_content,
        source_url="https://northwestcomfortsolutions.com/",
        anchor_hrefs=[
            {"url": "https://northwestcomfortsolutions.com/contact", "is_internal": True, "label": "Contact"},
            {"url": "https://northwestcomfortsolutions.com/privacy-policy", "is_internal": True, "label": "Privacy Policy"},
        ],
    )


def sparse_lead() -> dict:
    return make_base_lead(
        raw_html="<html><body></body></html>",
        text_content="",
        source_url="https://example.com/",
        page_title="",
        phone_number="",
        address="",
        rating_count=0,
        anchor_hrefs=[],
        robots_exists=False,
        sitemap_exists=False,
    )


def smma_candidate_with_socials() -> dict:
    raw_html = """
    <html>
      <head>
        <title>Rose City Auto Detail</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        <h1>Rose City Auto Detail</h1>
        <p>Auto detailing and ceramic coating in Portland.</p>
        <p>Book an appointment today.</p>
        <a href="/contact">Contact</a>
        <a href="https://instagram.com/rosecitydetail">Instagram</a>
        <a href="https://facebook.com/rosecitydetail">Facebook</a>
      </body>
    </html>
    """
    text_content = (
        "Rose City Auto Detail auto detailing and ceramic coating in Portland. "
        "Book an appointment today. Follow us on Instagram and Facebook."
    )
    return make_base_lead(
        raw_html=raw_html,
        text_content=text_content,
        source_url="https://rosecityautodetail.com/",
        anchor_hrefs=[
            {"url": "https://rosecityautodetail.com/contact", "is_internal": True, "label": "Contact"},
            {"url": "https://instagram.com/rosecitydetail", "is_internal": False, "label": "Instagram"},
            {"url": "https://facebook.com/rosecitydetail", "is_internal": False, "label": "Facebook"},
        ],
    )


def cross_campaign_lead() -> dict:
    raw_html = """
    <html>
      <head>
        <title>Rapid Response HVAC</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        <h1>Rapid Response HVAC</h1>
        <p>Emergency heating and cooling repair in Portland.</p>
        <p>Call now for same-day service.</p>
        <a href="tel:5035552222">Call Now</a>
        <a href="/contact">Contact</a>
      </body>
    </html>
    """
    text_content = (
        "Rapid Response HVAC emergency heating and cooling repair in Portland. "
        "Call now for same-day service."
    )
    return make_base_lead(
        raw_html=raw_html,
        text_content=text_content,
        source_url="https://rapidresponsehvac.com/",
        phone_number="503-555-2222",
        anchor_hrefs=[
            {"url": "https://rapidresponsehvac.com/contact", "is_internal": True, "label": "Contact"},
        ],
    )
