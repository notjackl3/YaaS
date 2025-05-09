import multiprocessing
from typing import Optional
import shutil
from PIL import Image
import numpy as np
import io
from dotenv import load_dotenv
import os
import subprocess
from skimage.metrics import structural_similarity as ssim
import cv2
import time
import urllib.parse
import tempfile
from .extras.uploader import Uploader, get_authenticated_service
from .extras.downloader import Downloader

pixel_to_bit = {(255, 255, 255): "00",
                (255, 0, 0): "01",
                (0, 255, 0): "10",
                (0, 0, 255): "11"}

bit_to_pixel = {"00": (255, 255, 255),
                "01": (255, 0, 0),
                "10": (0, 255, 0),
                "11": (0, 0, 255)}

target_colors = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
}

IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080
BLOCKS_DIMENSION = 4
BLOCKS_PER_IMAGE = int((IMAGE_WIDTH * IMAGE_HEIGHT) / BLOCKS_DIMENSION ** 2)

load_dotenv()
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
CLIENT_SECRET_FILE = os.getenv('CLIENT_SECRET_FILE')
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CLIENT_SECRET_FILE
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"


def extract_youtube_video_id(yt_video_link):
    url_data = urllib.parse.urlparse(yt_video_link)
    video_id_output = url_data.path[1:]
    return video_id_output


def _similar(img1, img2, threshold=0.9):
    if img1 is None or img2 is None:
        return False
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    score, _ = ssim(gray1, gray2, full=True)
    return score > threshold


def _closest_color(pixel, palette, black_threshold=40):
    pixel = np.array(pixel)

    if np.linalg.norm(pixel) > black_threshold and (0, 0, 0) in palette.values():
        palette = {name: color for name, color in palette.items() if color != (0, 0, 0)}

    min_dist = float('inf')
    closest = (0, 0, 0)

    for color in palette.values():
        dist = np.linalg.norm(pixel - np.array(color))
        if dist < min_dist:
            min_dist = dist
            closest = color

    return tuple(closest)


def _create_grid_4x4(dx, dy):
    order = [(dx + 1, dy + 1), (dx + 1, dy + 2), (dx + 2, dy + 1), (dx + 2, dy + 2),
             (dx + 1, dy), (dx + 3, dy + 1), (dx + 2, dy + 3), (dx, dy + 2),
             (dx + 2, dy), (dx + 3, dy + 2), (dx + 1, dy + 3), (dx, dy + 1),
             (dx, dy), (dx + 3, dy), (dx, dy + 3), (dx + 3, dy + 3)]
    return order


def wait_for_processing(request, video_id, cooldown=20):
    youtube = get_authenticated_service(request)
    while True:
        try:
            video_request = youtube.videos().list(
                part="snippet,contentDetails,processingDetails",
                id=video_id
            )
            video_response = video_request.execute()
            video_item = video_response.get("items")[0]
            snippet = video_item.get("snippet", {})
            thumbnails = snippet.get("thumbnails", {})
            processing_details = video_item.get("processingDetails", {})

            if "maxres" in thumbnails:
                break
            elif processing_details and processing_details.get("processingStatus") == "succeeded":
                break
            else:
                time.sleep(cooldown)
        except:
            continue


def _draw_image(arr):
    image_array = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=np.uint8)
    i = 0
    while i < len(arr):
        for y in range(0, 1080, BLOCKS_DIMENSION):
            for x in range(0, 1920, BLOCKS_DIMENSION):
                if i == len(arr):
                    break
                image_array[y:y + BLOCKS_DIMENSION, x:x + BLOCKS_DIMENSION] = bit_to_pixel[arr[i]]
                i += 1
    image = Image.fromarray(image_array)
    return image


def _create_chunk(file):
    with open(file, "rb") as file1:
        content = file1.read()
        output = []

        for byte in content:
            bits = f"{byte:08b}"
            output.extend([bits[i:i + 2] for i in range(0, 8, 2)])

        if len(output) > BLOCKS_PER_IMAGE:
            return [output[i:i + BLOCKS_PER_IMAGE] for i in range(0, len(output), BLOCKS_PER_IMAGE)]
        else:
            return [output]


def _read_image(file):
    img = Image.open(file)
    pixels = img.load()

    output_bits = []
    for y in range(0, 1080, BLOCKS_DIMENSION):
        for x in range(0, 1920, BLOCKS_DIMENSION):
            color_count = {}
            grid = _create_grid_4x4(x, y)
            for i, (dx, dy) in enumerate(grid):
                small_block_value = _closest_color(pixels[dx, dy], target_colors)
                count = color_count.get(small_block_value, 0) + 1
                color_count[small_block_value] = count
                if count == 8:
                    break

            if (255, 255, 255) in color_count and color_count[(255, 255, 255)] == 8:
                pixel_value = (255, 255, 255)
            else:
                pixel_value = max(color_count, key=color_count.get)

                if pixel_value == (0, 0, 0):
                    break

            output_bits.append(pixel_to_bit[pixel_value])

    return output_bits


def compile_video(main_folder, chunks_folder, frame_rate=2):
    command = [
        "ffmpeg",
        "-y",
        "-framerate", f"{frame_rate}",
        "-i", f"{chunks_folder}/pixel-image%07d.png",
        "-c:v", "libx264",
        "-b:v", "100M",
        "-pix_fmt", "yuv420p",
        f"{main_folder}/output.mp4"
    ]
    subprocess.run(command, check=True)


def upload(request, main_folder, title) -> str:
    uploader = Uploader()
    print(f"Youtube video name: {title}")
    uploaded_link = uploader.upload_video(request, f"{main_folder}/output.mp4", title,
                                          "Youtube as a service. By Jack Le.")
    return uploaded_link


def process(main_folder, video_name, yt_video_link):
    downloader = Downloader(main_folder, video_name)
    downloader.download_video(yt_video_link)

    with tempfile.TemporaryDirectory() as returning_chunks_folder:
        vid_cap = cv2.VideoCapture(f'{main_folder}/{video_name}.mp4')
        success, image = vid_cap.read()
        prev_frame = None
        frame_index = 0

        while success:
            if not _similar(image, prev_frame):
                cv2.imwrite(f"{returning_chunks_folder}/pixel-image{frame_index:07d}.png", image)
                prev_frame = image.copy()
                frame_index += 1
            success, image = vid_cap.read()

        chunks_length = len(os.listdir(returning_chunks_folder))

        images = []
        bytes_list = []
        for id2 in range(chunks_length):
            images.append(f"{returning_chunks_folder}/pixel-image{id2:07d}.png")

        output_bits = []

        with multiprocessing.Pool(processes=8) as pool:
            results = pool.map(_read_image, images)

        for result in results:
            output_bits.extend(result)

        temp_export = "".join(output_bits)
        b_list = [int(temp_export[i:i + 8], 2) for i in range(0, len(temp_export), 8)]
        bytes_list.extend(b_list)

        with open(f"{main_folder}/restored-{video_name}", "wb") as file2:
            buffer = io.BufferedWriter(file2)
            buffer.write(bytearray(bytes_list))
            buffer.flush()


# def upload_image_to_s3(file_path, username):
#     buffer = BytesIO()
#     image.save(buffer, format='PNG')
#     buffer.seek(0)
#
#     prefix_path = f"{username}/images/"
#
#     with open(file_path, 'rb') as file:
#         file_name = f"{prefix_path}{os.path.basename(file_path)}"
#         s3_path = default_storage.save(file_name, ContentFile(file.read()))
#     # s3 = boto3.resource("s3")
#     # bucket = s3.Bucket("youtube-as-a-service")
#     # bucket.upload_fileobj()
#
#     return default_storage.url(s3_path)


def create_video(request, main_folder, chunks_folder, file_to_compress: str, video_name: str,
                 existing_link: Optional[str] = None):
    output_chunks = _create_chunk(file_to_compress)

    for image_id, chunk in enumerate(output_chunks):
        image = _draw_image(chunk)
        file_path = os.path.join(chunks_folder, f"pixel-image{image_id:07d}.png")
        image.save(file_path)
        # obj.output_images.append(image)

    if not existing_link:
        print("Uploading onto Youtube.")
        if len(os.listdir(chunks_folder)) > 5:
            compile_video(main_folder, chunks_folder, 5)  # Compile the video in 5 frame per seconds
        else:
            compile_video(main_folder, chunks_folder, 1)
        yt_video_link = upload(request, main_folder, video_name)
    else:
        yt_video_link = existing_link

    video_id_output = extract_youtube_video_id(yt_video_link)

    return yt_video_link, video_id_output


def main_upload_function(request, file_to_compress, video_name):
    with tempfile.TemporaryDirectory() as main_folder:
        with tempfile.TemporaryDirectory() as chunks_folder:
            existing_youtube_link = None
            yt_video_link, video_id = create_video(request, main_folder, chunks_folder, file_to_compress, video_name,
                                                   existing_youtube_link)
            print("Created. Uploading")

            print("First process attempt.")
            wait_for_processing(request, video_id)
            print("Uploaded. Processing.")

            return yt_video_link

            # process(main_folder, video_object)
            # print("Processed.")
            #
            # print(os.path.isfile(f"{main_folder}/restored-{os.path.basename(file_to_compress)}"))
            # dst = os.path.join(os.getcwd(), f"restored-{os.path.basename(file_to_compress)}")
            # shutil.copyfile(f"{main_folder}/restored-{os.path.basename(file_to_compress)}", dst)


def main_downloadgit merge temporary_function(video_name, yt_video_link):
    with tempfile.TemporaryDirectory() as main_folder:
        process(main_folder, video_name, yt_video_link)
        print("Processed.")

        print(os.path.isfile(f"{main_folder}/restored-{video_name}"))
        dst = os.path.join(os.getcwd(), f"restored-{video_name}")
        shutil.copyfile(f"{main_folder}/restored-{video_name}", dst)
        return dst


if __name__ == "__main__":
    main_upload_function(None, None, None)
    main_download_function(None, None)
