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
