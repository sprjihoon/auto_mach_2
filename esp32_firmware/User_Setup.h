// ==========================================================
// TFT_eSPI User_Setup.h for ESP32-2432S028 (Cheap Yellow Display)
// ==========================================================
// 
// Copy this file to: Arduino/libraries/TFT_eSPI/User_Setup.h
// (Replace the existing User_Setup.h in the library folder)
//
// Or edit the existing User_Setup.h in the TFT_eSPI library
// and uncomment/set the values as shown below.
// ==========================================================

#define USER_SETUP_INFO "ESP32-2432S028 CYD Setup"

// ==========================================================
// Display Driver - Try ST7789 for some CYD versions
// ==========================================================
// #define ILI9341_DRIVER

// ST7789 driver for some CYD boards
#define ST7789_DRIVER

// ==========================================================
// Display Resolution
// ==========================================================
#define TFT_WIDTH  240
#define TFT_HEIGHT 320

// ==========================================================
// ESP32-2432S028 (CYD) Pin Configuration
// ==========================================================
// The CYD uses specific pins for the TFT display

#define TFT_MISO 12
#define TFT_MOSI 13
#define TFT_SCLK 14
#define TFT_CS   15   // Chip select
#define TFT_DC    2   // Data/Command
#define TFT_RST  -1   // Reset (not connected, use -1)
#define TFT_BL   21   // Backlight (active HIGH)

// ==========================================================
// Touch Screen Pins (XPT2046) - CYD uses SEPARATE SPI bus!
// ==========================================================
#define TOUCH_CS   33    // T_CS
#define TOUCH_MOSI 32    // T_DIN (Touch Data In)
#define TOUCH_MISO 39    // T_DO  (Touch Data Out)
#define TOUCH_CLK  25    // T_CLK (Touch Clock)
// #define TOUCH_IRQ 36  // T_IRQ (optional interrupt)

// ==========================================================
// Fonts - Enable the fonts you need
// ==========================================================
#define LOAD_GLCD    // Original Adafruit 8 pixel font
#define LOAD_FONT2   // Small 16 pixel high font
#define LOAD_FONT4   // Medium 26 pixel high font
#define LOAD_FONT6   // Large 48 pixel high font
#define LOAD_FONT7   // 7 segment 48 pixel high font
#define LOAD_FONT8   // Large 75 pixel high font
#define LOAD_GFXFF   // FreeFonts

// Enable smooth fonts
#define SMOOTH_FONT

// ==========================================================
// SPI Frequency - Optimized for CYD
// ==========================================================
// Note: If you see screen noise/glitches, try lowering these values
// Try: 40MHz -> 27MHz -> 20MHz -> 15MHz
#define SPI_FREQUENCY  20000000      // 20 MHz (more stable)
#define SPI_READ_FREQUENCY  10000000  // 10 MHz read speed
#define SPI_TOUCH_FREQUENCY  2500000  // 2.5 MHz touch speed

// ==========================================================
// Additional Options
// ==========================================================
// Use HSPI port for TFT (default for CYD)
#define USE_HSPI_PORT

// If display colors are inverted, uncomment this:
#define TFT_INVERSION_OFF
// Or this:
// #define TFT_INVERSION_ON

// RGB/BGR color order - CYD typically uses BGR
#define TFT_RGB_ORDER TFT_BGR

// ==========================================================
// End of User_Setup.h
// ==========================================================
