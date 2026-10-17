// Productify Node desktop app. It holds no secrets and makes no network calls:
// every action is a request to the local agent service over its named pipe.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

const PIPE: &str = r"\\.\pipe\productify-node";
const OPS: &[&str] = &["status", "pair", "live", "limits", "emergency_stop", "logs"];

/// Forward one request to the agent. Only known operations and fields pass through.
#[tauri::command]
async fn agent(op: String, args: Option<Value>) -> Result<Value, String> {
    if !OPS.contains(&op.as_str()) {
        return Err(format!("unknown operation {op}"));
    }
    let mut req = json!({ "op": op });
    if let Some(Value::Object(m)) = args {
        for k in ["code", "rental_id", "token", "live", "memory_mb", "cpus", "disk_gb", "share_gpu", "max_gpu_temp_c"] {
            if let Some(v) = m.get(k) {
                req[k] = v.clone();
            }
        }
    }
    tokio::time::timeout(Duration::from_secs(60), call(req))
        .await
        .map_err(|_| "The Productify Node service didn't answer.".to_string())?
}

#[cfg(windows)]
async fn call(req: Value) -> Result<Value, String> {
    use tokio::net::windows::named_pipe::ClientOptions;
    let pipe = ClientOptions::new().open(PIPE).map_err(|_| {
        "The Productify Node service isn't running. Reinstall the app or start the service from Windows Services.".to_string()
    })?;
    let (rd, mut wr) = tokio::io::split(pipe);
    let mut line = serde_json::to_vec(&req).map_err(|e| e.to_string())?;
    line.push(b'\n');
    wr.write_all(&line).await.map_err(|e| e.to_string())?;
    let mut resp = String::new();
    BufReader::new(rd).read_line(&mut resp).await.map_err(|e| e.to_string())?;
    let v: Value = serde_json::from_str(&resp).map_err(|_| "Unexpected answer from the service.".to_string())?;
    if v["ok"].as_bool() == Some(true) {
        Ok(v.get("data").cloned().unwrap_or(Value::Null))
    } else {
        Err(v["error"].as_str().unwrap_or("The service refused the request.").to_string())
    }
}

#[cfg(not(windows))]
async fn call(_req: Value) -> Result<Value, String> {
    Err("Productify Node currently supports Windows only.".into())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            use tauri::Manager;
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_focus();
            }
        }))
        .invoke_handler(tauri::generate_handler![agent])
        .run(tauri::generate_context!())
        .expect("failed to start Productify Node");
}
