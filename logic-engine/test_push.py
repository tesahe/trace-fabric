import zmq
import lead_v1_pb2
import time
import uuid
from datetime import datetime, timezone

print("🚀 Starting Logic Engine Test Publisher")

# Standard synchronous ZMQ Context for a simple script
ctx = zmq.Context()
socket = ctx.socket(zmq.PUSH) # Must be PUSH to match FastAPI's PULL
socket.connect("tcp://127.0.0.1:5555")

# 1. Instantiate the Protobuf Object
lead = lead_v1_pb2.RawLead(
    id=str(uuid.uuid4()),
    source_url="https://tracefabric.io/about",
    company_name="TraceFabric Labs",
    raw_html="<html><body><h1>We build pipelines!</h1></body></html>",
    timestamp=datetime.now(timezone.utc).isoformat()
)

# 2. Add it to our Batch envelope
batch = lead_v1_pb2.LeadBatch()
batch.leads.append(lead) 

# 3. The exact mechanism bridging Rust and Python: binary serialization
payload = batch.SerializeToString()

# 4. Fire over bare TCP
print(f"📡 Pushing payload of size {len(payload)} bytes to port 5555...")
socket.send(payload)

time.sleep(1) # Allow socket buffer to flush before exiting
socket.close()
ctx.term()
print("✅ Test complete.")
