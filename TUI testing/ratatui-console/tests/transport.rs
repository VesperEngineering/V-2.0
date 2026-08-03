use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::windows::named_pipe::ServerOptions;
use vesper_ratatui_console::contract::Envelope;
use vesper_ratatui_console::launcher::{canonical_state_root, gateway_args, validate_pipe_name};
use vesper_ratatui_console::transport::{MAX_FRAME_BYTES, decode_frame_bytes, encode_frame_bytes};

#[test]
fn framing_is_unsigned_big_endian_and_handles_split_input() {
    let frame = encode_frame_bytes(br#"{"ok":true}"#).unwrap();
    assert_eq!(&frame[..4], &(11_u32.to_be_bytes()));
    for split in 0..frame.len() {
        assert!(decode_frame_bytes(&frame[..split]).unwrap().is_none());
    }
    assert_eq!(
        decode_frame_bytes(&frame).unwrap().unwrap(),
        br#"{"ok":true}"#
    );
}

#[test]
fn rejects_zero_oversized_and_malformed_frames() {
    assert!(encode_frame_bytes(&[]).is_err());
    assert!(encode_frame_bytes(&vec![b'x'; MAX_FRAME_BYTES + 1]).is_err());
    assert!(decode_frame_bytes(&0_u32.to_be_bytes()).is_err());
    assert!(decode_frame_bytes(&(1_048_577_u32.to_be_bytes())).is_err());
    assert!(decode_frame_bytes(&[0, 0, 0, 2, b'{', b'}', b'x']).is_err());
}

#[test]
fn launcher_validates_exact_pipe_and_builds_exact_direct_argv() {
    let name = r"\\.\pipe\vesper-v20-tui-0123456789abcdef";
    assert_eq!(validate_pipe_name(&format!("{name}\n")).unwrap(), name);
    for bad in [
        r"\\.\pipe\vesper-v20-tui-0123456789abcde",
        r"\\.\pipe\vesper-v20-tui-0123456789abcdefx",
        r"\\.\pipe\other-0123456789abcdef",
        "junk\nsecond",
    ] {
        assert!(validate_pipe_name(bad).is_err());
    }
    let root = canonical_state_root().expect("LOCALAPPDATA on Windows");
    let args = gateway_args(&root, name, 42);
    assert_eq!(
        args[0..5],
        [
            "run",
            "--locked",
            "vesper-tui-gateway",
            "--state-root",
            root.to_str().unwrap()
        ]
    );
    assert_eq!(args[5..], ["--pipe-name", name, "--parent-pid", "42"]);
    assert!(
        !args
            .iter()
            .any(|arg| arg.to_ascii_lowercase().contains("password"))
    );
}

#[tokio::test]
async fn retry_timeout_is_bounded() {
    let started = std::time::Instant::now();
    let result = vesper_ratatui_console::transport::PipeTransport::connect(
        r"\\.\pipe\vesper-v20-tui-ffffffffffffffff",
        Duration::from_millis(120),
    )
    .await;
    assert!(result.is_err());
    assert!(started.elapsed() < Duration::from_secs(1));
}

#[tokio::test]
async fn real_named_pipe_accepts_early_client_and_round_trips_envelope() {
    let name = format!(
        r"\\.\pipe\vesper-v20-tui-test-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    );
    let mut server = ServerOptions::new()
        .first_pipe_instance(true)
        .create(&name)
        .expect("create local test pipe");
    let mut client =
        vesper_ratatui_console::transport::PipeTransport::connect(&name, Duration::from_secs(1))
            .await
            .expect("client opens before server starts accepting");
    let server_task = tokio::spawn(async move {
        server.connect().await.unwrap();
        let mut header = [0_u8; 4];
        server.read_exact(&mut header).await.unwrap();
        let mut body = vec![0_u8; u32::from_be_bytes(header) as usize];
        server.read_exact(&mut body).await.unwrap();
        server.write_all(&header).await.unwrap();
        server.write_all(&body).await.unwrap();
    });
    let envelope: Envelope = serde_json::from_str(
        r#"{"schema_version":1,"message_id":"ping:1","sequence":1,"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z","message_type":"ping","payload":{"nonce":"n:1"}}"#,
    )
    .unwrap();
    client.send(&envelope).await.unwrap();
    assert_eq!(client.recv().await.unwrap(), envelope);
    server_task.await.unwrap();
}
