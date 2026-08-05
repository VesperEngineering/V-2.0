use std::process::ExitCode;

#[tokio::main]
async fn main() -> ExitCode {
    let intent =
        match vesper_ratatui_console::startup::parse_startup_args(std::env::args_os().skip(1)) {
            Ok(intent) => intent,
            Err(error) => {
                eprintln!("V20 console did not start: {error}");
                return ExitCode::FAILURE;
            }
        };
    match vesper_ratatui_console::app::run_with_startup_intent(intent).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("V20 console stopped: {error}");
            ExitCode::FAILURE
        }
    }
}
