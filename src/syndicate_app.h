// syndicate - ReXGlue Recompiled Project
//
// Customize your app by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#include <rex/rex_app.h>
#include <rex/runtime.h>
#include <rex/system/xmemory.h>

class SyndicateApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<SyndicateApp>(new SyndicateApp(ctx, "syndicate",
        PPCImageConfig));
  }

  // Development helper: dump the loaded (decrypted, decompressed) game image so
  // tools/find_missing_functions.py can scan it for function pointers.
  // Runs only when DUMP_IMAGE is set to an output path. The dump is
  // game data: keep it local, never commit or share it.
  void OnPostLoadXexImage() override {
    const char* out_path = std::getenv("DUMP_IMAGE");
    if (!out_path || !*out_path) return;
    constexpr uint32_t kImageBase = 0x82000000;  // REX_IMAGE_BASE
    constexpr uint32_t kImageSize = 0x01100000;  // REX_IMAGE_SIZE
    const uint8_t* host = runtime()->memory()->TranslateVirtual(kImageBase);
    std::FILE* f = std::fopen(out_path, "wb");
    if (!f) {
      std::fprintf(stderr, "[dump] cannot open %s\n", out_path);
      return;
    }
    const size_t written = std::fwrite(host, 1, kImageSize, f);
    std::fclose(f);
    std::fprintf(stderr, "[dump] wrote %zu bytes (base 0x%08X) to %s\n", written, kImageBase,
                 out_path);
  }

  // Other hooks available from rex::ReXApp:
  // void OnPostInitLogging() override {}
  // void OnPreSetup(rex::RuntimeConfig& config) override {}
  // void OnLoadXexImage(std::string& xex_image) override {}
  // void OnPostSetup() override {}
  // void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override {}
  // std::unique_ptr<rex::ui::ImGuiDialog> CreateAchievementsOverlay() override;
  // std::unique_ptr<rex::ui::AchievementNotificationDialog>
  // CreateAchievementNotificationDialog() override;
  // void OnShutdown() override {}
  // void OnConfigurePaths(rex::PathConfig& paths) override {}
};
