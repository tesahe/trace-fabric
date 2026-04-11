import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zmq
import lead_v1_pb2
import time
import uuid
from datetime import datetime, timezone

ctx = zmq.Context()
socket = ctx.socket(zmq.PUSH)
socket.connect("tcp://127.0.0.1:5555")

def make_batch(html: str, company: str, url: str) -> bytes:
    lead = lead_v1_pb2.RawLead(
        id=str(uuid.uuid4()),
        source_url=url,
        company_name=company,
        raw_html=html,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    batch = lead_v1_pb2.LeadBatch()
    batch.leads.append(lead)
    return batch.SerializeToString()

# PUSH 1: Should hit Tier 0 rejection (low word count)
socket.send(make_batch("<html><body><p>Short page.</p></body></html>", "Junk Corp", "http://junk.com"))
print("Sent: Junk (Tier 0 reject expected)")
time.sleep(1)

# PUSH 2: Should hit Tier 0 rejection (Shopify signature)
shopify_html = "<html><body>" + ("word " * 200) + '<script src="cdn.shopify.com/s/files/1/theme.js"></script></body></html>'
socket.send(make_batch(shopify_html, "Shopify Store", "http://shopify-store.com"))
print("Sent: Shopify (Tier 0 CMS reject expected)")
time.sleep(1)

# PUSH 3: Should PASS Tier 0 and hit Tier 1 LLM — real plumber content
plumber_html = """
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body>
<h1>Mike's Plumbing Services</h1>
<p>Serving the Denver metro area for over 20 years. We specialize in emergency pipe repair,
water heater installation, drain cleaning, and bathroom remodels. Family owned and operated.
Licensed and insured in the state of Colorado. Call us 24/7 at (303) 555-0198 for fast,
reliable service. We guarantee our work or your money back. No job too big or too small.
Ask about our senior discount and veteran pricing. We serve Denver, Aurora, Lakewood,
Littleton, and surrounding areas. Our team of certified plumbers is ready to help you
today. We use only top-grade materials and the latest tools to get the job done right
the first time.
We also offer annual maintenance plans, emergency weekend callouts, and free estimates on all new installations. Google-rated 4.9 stars with over 300 reviews from satisfied Denver homeowners.
Hours of operation: Monday through Friday 8am to 6pm, Saturday 9am to 4pm. Closed Sundays.
</p>
<p>Contact us: mike@mikesplumbing.com | 123 Main St, Denver CO 80201</p>
</body>
</html>
"""
socket.send(make_batch(plumber_html, "Mike's Plumbing", "http://mikesplumbing.com"))
print("Sent: Real business (Tier 1 LLM call expected)")
time.sleep(3)  # Give Tier 1 time to respond

socket.close()
ctx.term()
print("✅ All test payloads sent.")
