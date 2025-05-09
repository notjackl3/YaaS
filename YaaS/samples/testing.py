import tempfile

with tempfile.TemporaryDirectory() as temp_dir:
    # temp_dir is an auto-cleaned folder path

    print(temp_dir)
