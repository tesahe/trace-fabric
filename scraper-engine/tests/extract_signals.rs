use scraper::Html;
use scraper_engine::extract::{extract_anchor_hrefs, extract_page_signals, extract_text_content};
use scraper_engine::schema::UrlArtifact;

fn load_fixture(name: &str, base_url: &str) -> (Html, String, Vec<UrlArtifact>) {
    let path = format!("{}/tests/fixtures/{}", env!("CARGO_MANIFEST_DIR"), name);
    let html_str = std::fs::read_to_string(&path)
        .unwrap_or_else(|_| panic!("fixture not found: {}", path));
    let document = Html::parse_document(&html_str);
    let text_content = extract_text_content(&document);
    let anchor_hrefs = extract_anchor_hrefs(&document, base_url);
    (document, text_content, anchor_hrefs)
}

#[test]
fn signals_weak_hvac() {
    let (document, text_content, anchor_hrefs) =
        load_fixture("weak_hvac.html", "https://aaaheatingandcoolinginc.com/");
    let signals = extract_page_signals(&document, &text_content, &anchor_hrefs);
    insta::assert_debug_snapshot!(signals);
}

#[test]
fn signals_voice_ai_plumbing() {
    let (document, text_content, anchor_hrefs) =
        load_fixture("voice_ai_plumbing.html", "https://fastresponseplumbing.com/");
    let signals = extract_page_signals(&document, &text_content, &anchor_hrefs);
    insta::assert_debug_snapshot!(signals);
}

#[test]
fn signals_smma_socials() {
    let (document, text_content, anchor_hrefs) =
        load_fixture("smma_socials.html", "https://rosecityautodetail.com/");
    let signals = extract_page_signals(&document, &text_content, &anchor_hrefs);
    insta::assert_debug_snapshot!(signals);
}

#[test]
fn signals_sparse() {
    let (document, text_content, anchor_hrefs) =
        load_fixture("sparse.html", "https://example.com/");
    let signals = extract_page_signals(&document, &text_content, &anchor_hrefs);
    insta::assert_debug_snapshot!(signals);
}

#[test]
fn signals_full() {
    let (document, text_content, anchor_hrefs) =
        load_fixture("full_signals.html", "https://cityplumbing.com/");
    let signals = extract_page_signals(&document, &text_content, &anchor_hrefs);
    insta::assert_debug_snapshot!(signals);
}
