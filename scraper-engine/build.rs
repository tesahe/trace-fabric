use std::io::Result;

fn main() -> Result<()> {
    // when cargo build :
    // look here, invoke compiler, output

    // relative to Cargo.toml
    prost_build::compile_protos(&["../proto/lead_v1.proto"], &["../proto"])?;

    println!("cargo:rerun-if-changed=../proto/lead_v1.proto");

    Ok(())
}
