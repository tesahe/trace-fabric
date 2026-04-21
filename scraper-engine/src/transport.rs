use std::sync::{Arc, Mutex};
use prost::Message;
use tracing::{error, info};

use crate::schema;

pub fn send_lead_batch(
    zmq_socket: &Arc<Mutex<zmq::Socket>>,
    payload: schema::RawLead,
    initial_url: &str,
) {
    let mut batch = schema::LeadBatch { leads: vec![] };
    batch.leads.push(payload);

    let encoded = batch.encode_to_vec();

    match zmq_socket.lock() {
        Ok(socket) => {
            if let Err(e) = socket.send(encoded, 0) {
                error!(url = %initial_url, error = %e, "Failed to send payload over ZMQ");
            } else {
                info!(url = %initial_url, "Payload sent over ZMQ");
            }
        }
        Err(e) => {
            error!(url = %initial_url, error = %e, "Failed to acquire lock on ZMQ socket");
        }
    }
}
