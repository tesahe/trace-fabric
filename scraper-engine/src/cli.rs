use clap::{Args, Parser, Subcommand};


#[derive(Parser, Debug)]
#[command(name = "scraper-engine")]
#[command(about = "TraceFabric ingestion worker")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Subcommand, Debug)]
pub enum Command {
    Discover(DiscoverArgs),
    Url(UrlArgs),
}

#[derive(Args, Debug, Clone)]
pub struct DiscoverArgs {
    #[arg(long)]
    pub industry: String,
    #[arg(long)]
    pub location: String,
    #[arg(long, default_value_t = 3)]
    pub limit: usize,
    #[arg(long, default_value_t = 1)]
    pub max_pages: usize,
    #[arg(long)]
    pub run_id: String,
}

#[derive(Args, Debug, Clone)]
pub struct UrlArgs {
    #[arg(long)]
    pub website: String,
    #[arg(long)]
    pub run_id: String,
    #[arg(long, default_value = "")]
    pub industry: String,
    #[arg(long, default_value = "")]
    pub location: String,
}