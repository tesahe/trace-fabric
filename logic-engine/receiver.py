import zmq
import time
import lead_v1_pb2 as pb2


def main():
    print("Starting Python ZeroMQ Pull node...")

    context = zmq.Context()
    receiver = context.socket(zmq.PULL)
    
    receiver.connect("tcp://127.0.0.1:5555")
    print("Connected to Rust.  Waiting for messages...")

    message_count = 0
    start_time = None

    for _ in range(1000):
        raw_bytes = receiver.recv()

        if message_count == 0:
            start_time = time.perf_counter()

        batch = pb2.LeadBatch()
        batch.ParseFromString(raw_bytes)

        message_count += 1

    end_time = time.perf_counter()
    total_time_ms = (end_time - start_time) * 1000

    print(f"\n--- SPIKE RESULTS ---")
    print(f"Total Messages Received: {message_count}")
    print(f"Total Time (Receive + Decode): {total_time_ms:.2f} ms")
    print(f"Average Latency per message: {(total_time_ms / 1000):.4f} ms")
    print(f"Sample data received: ID = {batch.leads[0].id}, Company = {batch.leads[0].company_name}")

if __name__ == "__main__":
    main()
