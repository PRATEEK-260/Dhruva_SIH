FROM ghcr.io/osgeo/gdal:ubuntu-small-3.9.2

# The base image ships numpy via apt (no pip RECORD file), which collides with
# pip trying to upgrade it for rasterio/titiler's own numpy requirement — pip
# then refuses to uninstall a package it doesn't own. A venv sidesteps this
# entirely rather than stacking --ignore-installed on top of
# --break-system-packages: found by actually building this image, not assumed.
RUN apt-get update && apt-get install -y --no-install-recommends python3-pip python3-venv && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000
# Clients reach this service only through the /tiles strip-prefix proxy (Caddy,
# Vite). Without root-path, tilejson's own tile URLs omit /tiles, and the proxy
# answers them with the frontend's index.html instead of a PNG.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--root-path", "/tiles"]
