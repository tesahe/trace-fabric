use prost::Message;
use std::sync::mpsc::Receiver;
use zmq::Context;
use tracing::{error, info};

use crate::schema;


pub fn run_zmq_sender(
    receiver: Receiver<schema::RawLead>, 
    zmq_push_addr: String) {
        
    let context = Context::new();


    // creates socket object in memory, has no destiniation
    // context.socket returns Result<Socket, Error> - socket created if Ok
    let socket = match context.socket(zmq::PUSH) {
        Ok(s) => s, //opens resulting socket, bind to s, assign to socket
        Err(e) => {
            error!(error = %e, "Failed to create ZMQ PUSH socket");
            return; // exit function entirely
        }
    };

    // socket.connect returns Result<(), Error> - only care if it failed
    if let Err(e) = socket.connect(&zmq_push_addr) {
        error!(addr = %zmq_push_addr, error = %e, "Failed to connect ZMQ PUSH socket");
        return;
    };

    //connected succeeded if reached here
    info!(addr = %zmq_push_addr, "ZMQ sender thread ready");

    while let Ok(lead) = receiver.recv() {
        // create single item batch
        // can be changed to batch of size n in future
        let url = lead.initial_url.clone();
        let id = lead.id.clone();

        let encoded = schema::LeadBatch {leads: vec![lead] }.encode_to_vec();

        if let Err(e) = socket.send(encoded, 0) {
            error!(url = %url, id = %id, error = %e, "Failed to send payload over ZMQ");
        } else {
            info!(url = %url, id = %id, "Payload sent over ZMQ");
        }
    }
        
        


    info!("ZMQ sender thread exiting - all senders dropped");



}