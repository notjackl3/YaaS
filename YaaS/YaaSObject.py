import ntpath


class YaaSObject:
    def __init__(self, original_file: str = "", name: str = ""):
        self.name = name
        self.original_file = original_file
        self.original_file_folder = ntpath.basename(original_file)
        self.output_chunks = []
        self.output_images = []
        self.yt_video_link = ""
        self.yt_video_id = ""

    def get_time_taken(self):
        return f"{self._end_time - self._start_time} seconds."
