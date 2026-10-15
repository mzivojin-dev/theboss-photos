FROM python:3.12-slim

# ffmpeg renders the Compilations; DejaVu fonts draw titles and captions.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV OPENCV_LOG_LEVEL=ERROR

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Semantic search model weights, baked in so jobs and the embed service never download at run time.
# Keep in step with MODEL_NAME / PRETRAINED in src/photo_embeddings.py.
ENV HF_HOME=/app/hf
RUN python -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-16-SigLIP2', pretrained='webli'); open_clip.get_tokenizer('ViT-B-16-SigLIP2')"
ENV HF_HUB_OFFLINE=1

# YuNet face detector (OpenCV Zoo), to prefer photos with people in them.
ADD https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx ./face_detection_yunet.onnx
# Background music, public domain (CC0) on OpenGameArt:
#   https://opengameart.org/content/jazz-aug-4-2021 (Alex McCulloch)
#   https://opengameart.org/content/lofi-hip-hop-loop (omfgdude)
ADD https://opengameart.org/sites/default/files/relaxing_aug_4_2021_1_0.mp3 ./music/relaxing_aug_4_2021.mp3
ADD https://opengameart.org/sites/default/files/LofiLoop_2.ogg ./music/lofi_loop.ogg

COPY src/ ./src/

CMD ["python", "-m", "src.main"]
