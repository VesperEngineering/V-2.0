use std::process::ExitCode;

#[tokio::main]
async fn main() -> ExitCode {
    match vesper_ratatui_console::app::run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("V20 console stopped: {error}");
            ExitCode::FAILURE
        }
    }
}
