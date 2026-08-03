use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::windows::named_pipe::ServerOptions;
use vesper_ratatui_console::contract::Envelope;
use vesper_ratatui_console::launcher::{
    canonical_state_root, connect_started_gateway, discover_pipe_name_from_command, gateway_args,
    validate_pipe_name,
};
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

fn envelope(json: &str) -> Envelope {
    serde_json::from_str(json).unwrap()
}

async fn read_frame<R: AsyncReadExt + Unpin>(reader: &mut R) -> Vec<u8> {
    let mut header = [0_u8; 4];
    reader.read_exact(&mut header).await.unwrap();
    let mut body = vec![0_u8; u32::from_be_bytes(header) as usize];
    reader.read_exact(&mut body).await.unwrap();
    body
}

#[tokio::test]
async fn cancelled_receive_resumes_partial_header_and_body() {
    let (stream, mut peer) = tokio::io::duplex(8);
    let mut transport = vesper_ratatui_console::transport::PipeTransport::from_stream(stream);
    let expected = envelope(
        r#"{"schema_version":1,"message_id":"ping:1","sequence":1,"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z","message_type":"ping","payload":{"nonce":"n:1"}}"#,
    );
    let frame = encode_frame_bytes(&serde_json::to_vec(&expected).unwrap()).unwrap();
    peer.write_all(&frame[..7]).await.unwrap();
    assert!(
        tokio::time::timeout(Duration::from_millis(10), transport.recv())
            .await
            .is_err()
    );
    let writer = tokio::spawn(async move { peer.write_all(&frame[7..]).await.unwrap() });
    assert_eq!(transport.recv().await.unwrap(), expected);
    writer.await.unwrap();
}

#[tokio::test]
async fn cancelled_send_finishes_prior_frame_before_different_message() {
    let (stream, mut peer) = tokio::io::duplex(8);
    let mut transport = vesper_ratatui_console::transport::PipeTransport::from_stream(stream);
    let first = envelope(&format!(
        r#"{{"schema_version":1,"message_id":"auth:1","sequence":1,"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z","message_type":"auth-unlock","payload":{{"password":"{}"}}}}"#,
        "x".repeat(1024)
    ));
    let second = envelope(
        r#"{"schema_version":1,"message_id":"ping:2","sequence":2,"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z","message_type":"ping","payload":{"nonce":"n:2"}}"#,
    );
    assert!(
        tokio::time::timeout(Duration::from_millis(10), transport.send(&first))
            .await
            .is_err()
    );
    let peer_task = tokio::spawn(async move {
        let first_body = read_frame(&mut peer).await;
        let second_body = read_frame(&mut peer).await;
        (first_body, second_body)
    });
    transport.send(&second).await.unwrap();
    let (first_body, second_body) = peer_task.await.unwrap();
    assert_eq!(
        serde_json::from_slice::<Envelope>(&first_body).unwrap(),
        first
    );
    assert_eq!(
        serde_json::from_slice::<Envelope>(&second_body).unwrap(),
        second
    );
}

#[tokio::test]
async fn cancelled_same_send_resumes_without_duplicate_frame() {
    let (stream, mut peer) = tokio::io::duplex(8);
    let mut transport = vesper_ratatui_console::transport::PipeTransport::from_stream(stream);
    let message = envelope(&format!(
        r#"{{"schema_version":1,"message_id":"auth:1","sequence":1,"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z","message_type":"auth-unlock","payload":{{"password":"{}"}}}}"#,
        "x".repeat(1024)
    ));
    assert!(
        tokio::time::timeout(Duration::from_millis(10), transport.send(&message))
            .await
            .is_err()
    );
    let peer_task = tokio::spawn(async move {
        let body = read_frame(&mut peer).await;
        let duplicate =
            tokio::time::timeout(Duration::from_millis(50), read_frame(&mut peer)).await;
        (body, duplicate)
    });
    transport.send(&message).await.unwrap();
    let (body, duplicate) = peer_task.await.unwrap();
    assert_eq!(serde_json::from_slice::<Envelope>(&body).unwrap(), message);
    assert!(duplicate.is_err());
}

#[tokio::test]
async fn unrecoverable_io_poisons_transport() {
    let (stream, peer) = tokio::io::duplex(8);
    let mut transport = vesper_ratatui_console::transport::PipeTransport::from_stream(stream);
    drop(peer);
    assert!(transport.recv().await.is_err());
    assert!(transport.recv().await.is_err());
}

#[tokio::test]
async fn discovery_timeout_kills_and_waits_for_child() {
    let marker = unique_marker("hang");
    let mut command = tokio::process::Command::new("pwsh");
    command.args([
        "-NoProfile",
        "-Command",
        &format!(
            "Start-Sleep -Milliseconds 500; Set-Content -LiteralPath '{}' -Value orphaned",
            marker.display()
        ),
    ]);
    let started = std::time::Instant::now();
    assert!(
        discover_pipe_name_from_command(command, Duration::from_millis(30))
            .await
            .is_err()
    );
    assert!(started.elapsed() < Duration::from_secs(1));
    tokio::time::sleep(Duration::from_millis(600)).await;
    assert!(!marker.exists());
}

#[tokio::test]
async fn oversized_discovery_output_kills_child_without_waiting_for_exit() {
    let mut command = tokio::process::Command::new("pwsh");
    command.args([
        "-NoProfile",
        "-Command",
        "[Console]::Out.Write(('x' * 300)); Start-Sleep -Seconds 10",
    ]);
    let started = std::time::Instant::now();
    assert!(
        discover_pipe_name_from_command(command, Duration::from_secs(2))
            .await
            .is_err()
    );
    assert!(started.elapsed() < Duration::from_secs(1));
}

#[tokio::test]
async fn failed_started_gateway_connect_kills_and_waits_for_child() {
    let marker = unique_marker("start");
    let mut command = tokio::process::Command::new("pwsh");
    command.args([
        "-NoProfile",
        "-Command",
        &format!(
            "Start-Sleep -Milliseconds 500; Set-Content -LiteralPath '{}' -Value orphaned",
            marker.display()
        ),
    ]);
    let child = command.spawn().unwrap();
    assert!(
        connect_started_gateway(
            child,
            r"\\.\pipe\vesper-v20-tui-ffffffffffffffff",
            Duration::from_millis(30),
        )
        .await
        .is_err()
    );
    tokio::time::sleep(Duration::from_millis(600)).await;
    assert!(!marker.exists());
}

fn unique_marker(label: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "v20-tui-{label}-{}-{}.txt",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}
