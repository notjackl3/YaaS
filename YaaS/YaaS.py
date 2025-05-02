import multiprocessing

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
from google_auth_oauthlib.flow import InstalledAppFlow
from uploader import Uploader, get_authenticated_service
from downloader import Downloader
from YaaSObject import YaaSObject
import glob

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
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'


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
    order = [(dx + 1, dy + 1),
             (dx + 1, dy + 2),
             (dx + 2, dy + 1),
             (dx + 2, dy + 2),
             (dx + 1, dy),
             (dx + 3, dy + 1),
             (dx + 2, dy + 3),
             (dx, dy + 2),
             (dx + 2, dy),
             (dx + 3, dy + 2),
             (dx + 1, dy + 3),
             (dx, dy + 1),
             (dx, dy),
             (dx + 3, dy),
             (dx, dy + 3),
             (dx + 3, dy + 3)]
    return order


def wait_for_processing(video_id, cooldown=20):
    youtube = get_authenticated_service()

    while True:
        try:
            print("Process attempt.")
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


class YaaS:
    def __init__(self, width: int = IMAGE_WIDTH, height: int = IMAGE_HEIGHT, dimension: int = BLOCKS_DIMENSION) -> None:
        self.image_width = width
        self.image_height = height
        self.blocks_dimension = dimension
        self.blocks_per_image = int((width * IMAGE_HEIGHT) / BLOCKS_DIMENSION ** 2)

        self.main: YaaSObject = YaaSObject()

    def _draw_image(self, arr):
        image_array = np.zeros((self.image_height, self.image_width, 3), dtype=np.uint8)
        i = 0
        while i < len(arr):
            for y in range(0, 1080, self.blocks_dimension):
                for x in range(0, 1920, self.blocks_dimension):
                    if i == len(arr):
                        break
                    image_array[y:y + self.blocks_dimension, x:x + self.blocks_dimension] = bit_to_pixel[arr[i]]
                    i += 1
        image = Image.fromarray(image_array)
        return image

    def _create_chunk(self, file):
        with open(file, "rb") as file1:
            content = file1.read()
            output = []

            for byte in content:
                bits = f"{byte:08b}"
                output.extend([bits[i:i + 2] for i in range(0, 8, 2)])

            if len(output) > self.blocks_per_image:
                return [output[i:i + self.blocks_per_image] for i in range(0, len(output), self.blocks_per_image)]
            else:
                return [output]

    def _read_image(self, file):
        img = Image.open(file)
        pixels = img.load()

        output_bits = []
        for y in range(0, 1080, self.blocks_dimension):
            for x in range(0, 1920, self.blocks_dimension):
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

    def compile(self, frame_rate=2):
        command = [
            "ffmpeg",
            "-y",
            "-framerate", f"{frame_rate}",
            "-i", "chunks/pixel-image%07d.png",
            "-c:v", "libx264",
            "-b:v", "100M",
            "-pix_fmt", "yuv420p",
            "output.mp4"
        ]
        subprocess.run(command, check=True)

    def upload(self, title) -> str:
        uploader = Uploader()
        print(f"Youtube video name: {title}")
        uploaded_link = uploader.upload_video("output.mp4", title, "Youtube as a service. By Jack Le.")
        return uploaded_link

    def process(self):
        os.makedirs("returning-chunks", exist_ok=True)
        files = glob.glob('returning-chunks/*')
        for f in files:
            os.remove(f)

        chunks_length = len(self.main.output_chunks)
        file_name = self.main.name
        link = self.main.yt_video_link
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_folder = os.path.join(script_dir, "downloads")

        downloader = Downloader(output_folder, file_name)
        downloader.download_video(link)

        vid_cap = cv2.VideoCapture(f'downloads/{file_name}.mp4')
        success, image = vid_cap.read()
        prev_frame = None
        frame_index = 0
        while success:
            if not _similar(image, prev_frame):
                cv2.imwrite(f"returning-chunks/pixel-image{frame_index:07d}.png", image)
                prev_frame = image.copy()
                frame_index += 1
            success, image = vid_cap.read()

        images = []
        bytes_list = []
        for id2 in range(chunks_length):
            images.append(f"returning-chunks/pixel-image{id2:07d}.png")

        output_bits = []

        with multiprocessing.Pool(processes=8) as pool:
            results = pool.map(self._read_image, images)

        for result in results:
            output_bits.extend(result)

        temp_export = "".join(output_bits)
        b_list = [int(temp_export[i:i + 8], 2) for i in range(0, len(temp_export), 8)]
        bytes_list.extend(b_list)

        with open(f"restored-{os.path.basename(yaas.main.original_file)}", "wb") as file2:
            buffer = io.BufferedWriter(file2)
            buffer.write(bytearray(bytes_list))
            buffer.flush()

    def create_video(self, file_name: str, title: str, existing_link: str = None) -> (YaaSObject, str):
        obj = YaaSObject(file_name, title)
        obj._start_time = time.time()
        obj.output_chunks = self._create_chunk(obj.original_file)

        os.makedirs("chunks", exist_ok=True)
        files = glob.glob('chunks/*')
        for f in files:
            os.remove(f)
        for image_id, chunk in enumerate(obj.output_chunks):
            image = self._draw_image(chunk)
            image.save(f"chunks/pixel-image{image_id:07d}.png")
            obj.output_images.append(image)
        print(f"Total frames: {len(obj.output_images)}")

        if not existing_link:
            print("Uploading onto Youtube.")
            if len(os.listdir("chunks")) > 5:
                self.compile(5) # Compile the video in 5 frame per seconds
            else:
                self.compile(1)
            obj.yt_video_link = self.upload(obj.name)
        else:
            obj.yt_video_link = existing_link

        url_data = urllib.parse.urlparse(obj.yt_video_link)
        video_id = url_data.path[1:]
        obj._end_time = time.time()

        return obj, video_id


if __name__ == "__main__":
    file_to_compress = input("Please enter the name of the file you want to send to youtube: ")

    yaas = YaaS(IMAGE_WIDTH, IMAGE_HEIGHT, BLOCKS_DIMENSION)
    existing_youtube_link = None
    yaas.main, yaas.main.yt_video_id = yaas.create_video(file_to_compress, "TestingSample1", existing_youtube_link)
    print("Created. Uploading")

    print("First process attempt.")
    wait_for_processing(yaas.main.yt_video_id)
    print("Uploaded. Processing.")

    yaas.process()
    print("Processed.")
