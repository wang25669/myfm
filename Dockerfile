FROM python:3.9-slim
WORKDIR /app/myfm
COPY myfm /app/myfm
RUN pip install -r requirements.txt
EXPOSE 5000
CMD ["python", "app.py"]
