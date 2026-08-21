from PIL import Image
import win32print

def png_a_zpl_hex(ruta_imagen, ancho_max_px=300):
    img = Image.open(ruta_imagen).convert("L")
    ratio = ancho_max_px / img.width
    img = img.resize((ancho_max_px, int(img.height * ratio)))
    img = img.point(lambda x: 0 if x < 128 else 255, mode="1")

    width_bytes = (img.width + 7) // 8
    total_bytes = width_bytes * img.height

    hex_data = ""
    pixels = img.load()
    for y in range(img.height):
        byte = 0
        bits_filled = 0
        for x in range(img.width):
            bit = 0 if pixels[x, y] == 0 else 1
            byte = (byte << 1) | (0 if bit == 0 else 1)
            bits_filled += 1
            if bits_filled == 8:
                hex_data += f"{byte:02X}"
                byte = 0
                bits_filled = 0
        if bits_filled > 0:
            byte = byte << (8 - bits_filled)
            hex_data += f"{byte:02X}"

    return hex_data, width_bytes, total_bytes, img.height

def subir_logo(nombre_impresora, ruta_logo, nombre_logo_zpl="LOGO.GRF"):
    hex_data, width_bytes, total_bytes, height = png_a_zpl_hex(ruta_logo)

    zpl = f"^XA\n~DG{nombre_logo_zpl},{total_bytes},{width_bytes},{hex_data}\n^XZ\n"

    hPrinter = win32print.OpenPrinter(nombre_impresora)
    try:
        hJob = win32print.StartDocPrinter(hPrinter, 1, ("Subir Logo", None, "RAW"))
        win32print.StartPagePrinter(hPrinter)
        win32print.WritePrinter(hPrinter, zpl.encode("utf-8"))
        win32print.EndPagePrinter(hPrinter)
        win32print.EndDocPrinter(hPrinter)
    finally:
        win32print.ClosePrinter(hPrinter)

    print("Listo. Logo subido como", nombre_logo_zpl)

if __name__ == "__main__":
    subir_logo("POS Printer 203DPI  Series", r"C:\Users\USER\Documents\LOGO_IMPRESORA\LOGO.png")
