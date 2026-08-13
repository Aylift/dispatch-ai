




use tauri::{
  image::Image,
  menu::{Menu, MenuItem},
  tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
  Manager, WebviewWindow,
};








fn show_window(win: &WebviewWindow) {
  // Bring the HUD back and focus it when restored from the tray.
  let _ = win.show();
  let _ = win.set_focus();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      if cfg!(debug_assertions) {
        use tauri_plugin_log::{Target, TargetKind};
        app.handle().plugin(
          tauri_plugin_log::Builder::new()
            .level(log::LevelFilter::Info)
            .targets([
              Target::new(TargetKind::Stdout),
              Target::new(TargetKind::LogDir { file_name: Some("dispatch.log".into()) }),
            ])
            .build(),
        )?;
      }

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
    .invoke_handler(tauri::generate_handler![hide_window])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

/// Hide the HUD into the tray (called from the header hide button). Restore
/// via the tray "Show" or by left-clicking the tray icon.
#[tauri::command]
fn hide_window(app: tauri::AppHandle) {
  if let Some(win) = app.get_webview_window("main") {
    let _ = win.hide();
  }
}


