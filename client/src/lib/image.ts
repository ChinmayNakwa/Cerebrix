const MAX_EDGE = 1568;
const JPEG_QUALITY = 0.85;

// Downscales an image and returns raw base64 JPEG (no data: prefix), which is
// what the backend expects. Falls back to the original bytes if decoding fails.
export async function imageToBase64(file: File): Promise<string> {
    try {
        const bitmap = await createImageBitmap(file);
        const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(bitmap.width * scale);
        canvas.height = Math.round(bitmap.height * scale);
        const ctx = canvas.getContext('2d')!;
        ctx.fillStyle = '#fff'; // JPEG has no alpha, so transparent PNGs would turn black
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        bitmap.close();
        return canvas.toDataURL('image/jpeg', JPEG_QUALITY).split(',')[1];
    } catch {
        return fileToBase64(file);
    }
}

function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve((reader.result as string).split(',')[1]);
        reader.onerror = error => reject(error);
    });
}
