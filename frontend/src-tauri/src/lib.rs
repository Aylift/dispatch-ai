




use std::{
  fs,
  path::PathBuf,
  process::{Child, Command, Stdio},
  sync::Mutex,
};

use tauri::{
  image::Image,
  menu::{Menu, MenuItem},
  tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
  Manager, RunEvent, WebviewWindow,
};

// ---------------------------------------------------------------------------
// Backend lifecycle
//
// The Tauri app is the "master": it spawns the FastAPI backend (pythonw.exe,
// no console window) on startup, and kills it on exit. The SQLite database
// lives on the Windows host, outside the repo, at DISPATCH_DATA_DIR (default
// %USERPROFILE%\.dispatch-ai), so data survives reinstalls and is easy to
// back up with scripts/backup.ps1.
// ---------------------------------------------------------------------------

struct BackendProcess {
  child: Child,
  pid: u32,
}

impl BackendProcess {
  fn start() -> Option<Self> {
    let backend_dir = resolve_backend_dir()?;
    let python = backend_dir.join(".venv").join("Scripts").join("pythonw.exe");
    if !python.exists() {
      log::warn!("backend venv python not found at {}", python.display());
      return None;
    }

            // SQLAlchemy accepts POSIX-style paths in the URL; normalize backslashes
    // so a Windows path like C:\Users\... works in `sqlite+aiosqlite:///...`.
    let db_path = backend_data_dir()
      .join("dispatch.db")
      .display()
      .to_string()
      .replace('\\', "/");
    let database_url = format!("sqlite+aiosqlite:///{db_path}");

    // Log dir for backend output (uvicorn writes its own logs here too).
    let logs_dir = backend_data_dir().join("logs");
    let _ = fs::create_dir_all(&logs_dir);
    // Append, don't truncate, so a backend restart keeps history.
    let log_file = fs::OpenOptions::new()
      .create(true)
      .append(true)
      .open(logs_dir.join("backend.log"));

    let mut cmd = Command::new(&python);
    cmd
      .current_dir(&backend_dir)
      .arg("-m")
      .arg("uvicorn")
      .arg("main:app")
      .arg("--host")
      .arg("127.0.0.1")
      .arg("--port")
      .arg("8000")
      .env("DATABASE_URL", database_url);

    // Redirect the child's stdout/stderr to a log file. Without this, a
    // windowed (no-console) app leaves the child with no stdio at all, and
    // uvicorn crashes on `sys.stdout.isatty()`. Piping to a file fixes that
    // AND captures backend logs for debugging.
    if let Ok(file) = log_file {
      match file.try_clone() {
        Ok(err_file) => {
          cmd.stdout(Stdio::from(file));
          cmd.stderr(Stdio::from(err_file));
        }
        Err(e) => {
          log::warn!("could not clone backend log handle: {e}");
        }
      }
    }

    // Spawn with no console window so nothing pops up when the HUD starts.
    #[cfg(windows)]
    {
      use std::os::windows::process::CommandExt;
      const CREATE_NO_WINDOW: u32 = 0x0800_0000;
      cmd.creation_flags(CREATE_NO_WINDOW);
    }

    log::info!(
      "spawning backend: {} -m uvicorn main:app --port 8000",
      python.display()
    );
    match cmd.spawn() {
      Ok(child) => {
        let pid = child.id();
        log::info!("backend spawned (pid {pid})");
        Some(Self { child, pid })
      }
      Err(e) => {
        log::error!("failed to spawn backend: {e}");
        None
      }
    }
  }

  fn stop(&mut self) {
    // Kill the direct child first, then force-kill the whole process tree so
    // uvicorn (and any worker it spawned) can't survive the HUD quitting.
    let _ = self.child.kill();
    let _ = self.child.wait();
    #[cfg(windows)]
    {
      use std::os::windows::process::CommandExt;
      use std::process::Command as StdCommand;
      let _ = StdCommand::new("taskkill")
        .args(["/PID", &self.pid.to_string(), "/T", "/F"])
        .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
        .status();
    }
    // Belt-and-suspenders: also kill any process still bound to the backend
    // port. A stale backend from a previous (crashed / force-killed) session
    // can outlive the HUD and hold :8000, which shadows the fresh backend the
    // next launch spawns. Killing by port guarantees a clean slate.
    kill_port_8000();
    log::info!("backend process stopped");
  }
}

/// Force-kill whatever is currently listening on the backend port (8000).
/// Used on exit so a stale backend can never survive the HUD and shadow the
/// next launch. Parses `netstat -ano` for the owning PID, then taskkills it.
#[cfg(windows)]
fn kill_port_8000() {
  use std::os::windows::process::CommandExt;
  use std::process::Command as StdCommand;
  const CREATE_NO_WINDOW: u32 = 0x0800_0000;

  let out = StdCommand::new("netstat")
    .args(["-ano"])
    .creation_flags(CREATE_NO_WINDOW)
    .output();
  let Ok(out) = out else { return };
  let Ok(text) = String::from_utf8(out.stdout) else { return };

  let mut pids: Vec<String> = Vec::new();
  for line in text.lines() {
    // Match the local address bound to :8000 (LISTENING or ESTABLISHED).
    if line.contains(":8000") && line.contains("LISTENING") {
      if let Some(pid) = line.split_whitespace().last() {
        if !pid.is_empty() && pid.chars().all(|c| c.is_ascii_digit()) {
          pids.push(pid.to_string());
        }
      }
    }
  }
  pids.sort();
  pids.dedup();
  for pid in pids {
    log::info!("killing stale backend on :8000 (pid {pid})");
    let _ = StdCommand::new("taskkill")
      .args(["/PID", &pid, "/T", "/F"])
      .creation_flags(CREATE_NO_WINDOW)
      .status();
  }
}

/// Locate the `backend/` source folder for whichever layout we're running in:
///   1. `DISPATCH_BACKEND_DIR` explicit override (set by setup scripts / portable installs)
///   2. a `backend` folder next to the running executable (portable layout)
///   3. the repo dev layout (`frontend/src-tauri` -> `../../backend`)
fn resolve_backend_dir() -> Option<PathBuf> {
  if let Ok(dir) = std::env::var("DISPATCH_BACKEND_DIR") {
    let p = PathBuf::from(dir);
    if p.join("main.py").exists() {
      log::info!("backend dir (DISPATCH_BACKEND_DIR): {}", p.display());
      return Some(p);
    }
  }

  if let Ok(exe) = std::env::current_exe() {
    if let Some(parent) = exe.parent() {
      let p = parent.join("backend");
      if p.join("main.py").exists() {
        log::info!("backend dir (next to exe): {}", p.display());
        return Some(p);
      }
    }
  }

  let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../backend");
  if dev.join("main.py").exists() {
    log::info!("backend dir (dev): {}", dev.display());
    return Some(dev);
  }

  log::error!("could not locate the backend/ source folder");
  None
}

/// Where the SQLite database lives on the Windows host (outside the repo), so
/// it survives reinstalls and is easy to back up with scripts/backup.ps1.
fn backend_data_dir() -> PathBuf {
  // 1) Explicit process env var.
  if let Ok(dir) = std::env::var("DISPATCH_DATA_DIR") {
    let p = PathBuf::from(dir);
    let _ = std::fs::create_dir_all(&p);
    return p;
  }

  // 2) The repo-root .env (same source Docker/setup scripts use).
  let repo_env = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../.env");
  if let Ok(contents) = std::fs::read_to_string(&repo_env) {
    for line in contents.lines() {
      let line = line.trim();
      if let Some(value) = line.strip_prefix("DISPATCH_DATA_DIR=") {
        let p = PathBuf::from(value.trim().trim_matches('"').trim_matches('\''));
        let _ = std::fs::create_dir_all(&p);
        return p;
      }
    }
  }

  // 3) Fallback default, matching the docs.
  let home = std::env::var("USERPROFILE").unwrap_or_else(|_| ".".into());
  let p = PathBuf::from(home).join(".dispatch-ai");
  let _ = std::fs::create_dir_all(&p);
  p
}

fn show_window(win: &WebviewWindow) {
  // Bring the HUD back and focus it when restored from the tray.
  let _ = win.show();
  let _ = win.set_focus();
}

/// Dock the HUD to the right edge of the primary monitor's work area and make
/// it as tall as the monitor. Falls back to the configured size if no monitor
/// is available.
fn dock_to_right(app: &tauri::AppHandle) {
  let Some(win) = app.get_webview_window("main") else {
    return;
  };
  // Dock to the PRIMARY monitor. Using current_monitor() here is a bug: if the
  // window is ever placed on a secondary monitor with negative coordinates
  // (e.g. a display arranged above the primary), it docks to that off-screen
  // work area and the HUD becomes invisible while the OS still reports it as
  // "visible". The primary monitor is always on-screen.
  let Some(monitor) = win.primary_monitor().ok().flatten() else {
    return;
  };
  let work = monitor.work_area();
  // work_area() is in PHYSICAL pixels. The desired 640 is a LOGICAL width, so
  // scale it by the monitor's DPI factor — otherwise on a high-DPI display the
  // window is squashed to 640 physical px (e.g. 320 logical at 200%).
  let scale = monitor.scale_factor();
  let width = (640.0 * scale).round() as u32;
  let height = work.size.height;
  let x = work.position.x + work.size.width as i32 - width as i32;
  let y = work.position.y;
  log::info!(
    "dock: monitor={:?} scale={} work={:?}, target=({}, {}, {}x{})",
    monitor.name(),
    monitor.scale_factor(),
    work,
    x,
    y,
    width,
    height
  );
  win.set_size(tauri::PhysicalSize::new(width, height)).unwrap();
  win.set_position(tauri::PhysicalPosition::new(x, y)).unwrap();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
      // A second instance was launched: focus the existing HUD window instead
      // of spawning a new one.
      if let Some(win) = app.get_webview_window("main") {
        show_window(&win);
      }
    }))
    .plugin(tauri_plugin_autostart::Builder::new().build())
        .setup(|app| {
      // Logging always on. In debug it also prints to stdout; in all builds it
      // appends to a per-app log file so we can always see what happened.
      {
        use tauri_plugin_log::{Target, TargetKind};
        let mut targets = vec![Target::new(TargetKind::LogDir {
          file_name: Some("dispatch.log".into()),
        })];
        if cfg!(debug_assertions) {
          targets.push(Target::new(TargetKind::Stdout));
        }
        app.handle().plugin(
          tauri_plugin_log::Builder::new()
            .level(log::LevelFilter::Info)
            .targets(targets)
            .build(),
        )?;
      }

      // Launch with the OS at logon: register the autostart Run/Startup key
      // pointing at this executable. Idempotent. Only in release builds — a
      // debug build loads its UI from the vite dev server (:5173), which isn't
      // running at logon, so autostarting it would spawn a blank window that
      // holds the single-instance lock and blocks later manual launches.
      if !cfg!(debug_assertions) {
        if let Err(e) = tauri_plugin_autostart::ManagerExt::autolaunch(app).enable() {
          log::warn!("failed to enable autostart: {e}");
        }
      }

      // Dock the HUD to the right edge of the primary monitor, full height.
      // The window is created hidden (visible:false) so this resize/move happens
      // before WebView2 paints; the frontend calls .show() once Vue has mounted.
      dock_to_right(app.handle());

      // Kill any orphaned backend still holding :8000 from a prior launch so
      // the fresh spawn can bind. (stop() only runs on a clean exit.)
      #[cfg(windows)]
      kill_port_8000();

      // Spawn the backend so the HUD has a running API.
      let backend = BackendProcess::start();
      app.manage(Mutex::new(backend));

      // Menu + system tray: the frameless, skip-taskbar HUD can't be closed
      // or restored from the taskbar, so the tray is the way in and out.
      let show = MenuItem::with_id(app, "show", "Show", true, None::<&str>)?;
      let hide = MenuItem::with_id(app, "hide", "Hide", true, None::<&str>)?;
      let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
      let menu = Menu::with_items(app, &[&show, &hide, &quit])?;

      let icon = Image::from_bytes(include_bytes!("../icons/32x32.png"))?;

            let _tray = TrayIconBuilder::with_id("main-tray")
        .icon(icon)
        .tooltip("Dispatch AI — HUD")
        .menu(&menu)
        .on_menu_event(|app, event| match event.id.as_ref() {
          "show" => {
            if let Some(win) = app.get_webview_window("main") {
              show_window(&win);
            }
          }
          "hide" => {
            if let Some(win) = app.get_webview_window("main") {
              let _ = win.hide();
            }
          }
                    "quit" => {
            app.exit(0);
          }
          _ => {}
        })
        .on_tray_icon_event(|tray, event| {
          // Left-click (or double-click) opens the HUD directly. On Windows the
          // menu is shown automatically on right-click when a menu is set, so
          // we only need to act on a left-click here.
          if let TrayIconEvent::Click {
            button: MouseButton::Left,
            button_state: MouseButtonState::Up,
            ..
          } = event
          {
                        if let Some(win) = tray.app_handle().get_webview_window("main") {
              show_window(&win);
            }
          }
        })
        .show_menu_on_left_click(false)
        .build(app)?;

      Ok(())
    })
    .invoke_handler(tauri::generate_handler![hide_window, backend_status])
    .build(tauri::generate_context!())
    .expect("error building tauri application")
    .run(|app, event| {
      // Shut the backend down together with the HUD.
      if let RunEvent::Exit = event {
        if let Ok(mut backend) = app.state::<Mutex<Option<BackendProcess>>>().inner().lock() {
          if let Some(b) = backend.as_mut() {
            b.stop();
          }
        }
      }
    });
}

/// Hide the HUD into the tray (called from the header hide button). Restore
/// via the tray "Show" or by left-clicking the tray icon.
#[tauri::command]
fn hide_window(app: tauri::AppHandle) {
  if let Some(win) = app.get_webview_window("main") {
    let _ = win.hide();
  }
}

/// Return diagnostics the HUD can surface when the backend/DB can't be reached.
/// `log_path` points at the backend log file so the user knows where to look.
#[tauri::command]
fn backend_status(app: tauri::AppHandle) -> serde_json::Value {
  use serde_json::json;

  let running = app
    .state::<Mutex<Option<BackendProcess>>>()
    .inner()
    .lock()
    .map(|b| b.is_some())
    .unwrap_or(false);

  json!({
    "running": running,
    "log_path": backend_data_dir().join("logs").join("backend.log").display().to_string(),
  })
}
