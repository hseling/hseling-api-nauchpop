from os import environ
from io import BytesIO, SEEK_END, SEEK_SET
from uuid import uuid4


from celery import Celery, result
from werkzeug.utils import secure_filename

from minio import Minio
from minio.error import (ResponseError, BucketAlreadyOwnedByYou,
                         BucketAlreadyExists)

CELERY_BROKER_URL = environ["CELERY_BROKER_URL"]
CELERY_RESULT_BACKEND = environ["CELERY_RESULT_BACKEND"]

MINIO_URL = environ["MINIO_URL"]
MINIO_ACCESS_KEY = environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = environ["MINIO_SECRET_KEY"]
MINIO_BUCKET_NAME = environ['MINIO_BUCKET_NAME']

ALLOWED_EXTENSIONS = ['txt']
UPLOAD_PREFIX = 'upload/'
PROCESSED_PREFIX = 'processed/'
NER_PREFIX = 'ner_'
TOPIC_PREFIX = 'topic_'
RB_PREFIX = 'rb_'
TERM_PREFIX = 'term_'

ERROR_NO_FILE_PART = "ERROR_NO_FILE_PART"
ERROR_NO_SELECTED_FILE = "ERROR_NO_SELECTED_FILE"
ERROR_NO_SUCH_FILE = "ERROR_NO_SUCH_FILE"
ERROR_NO_PROCESS_TYPE_SPECIFIED = "ERROR_NO_PROCESS_TYPE_SPECIFIED"

ENDPOINT_ROOT = "ENDPOINT_ROOT"
ENDPOINT_SCRAP = "ENDPOINT_SCRAP"
ENDPOINT_UPLOAD = "ENDPOINT_UPLOAD"
ENDPOINT_PROCESS = "ENDPOINT_PROCESS"
ENDPOINT_STATUS = "ENDPOINT_STATUS"
ENDPOINT_QUERY = "ENDPOINT_QUERY"

RESTRICTED_MODE = environ["RESTRICTED_MODE"]


def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery


minioClient = Minio(MINIO_URL,
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    secure=False)


def with_minio(fn):
    def fn_inner(*args, **kwargs):
        try:
            minioClient.make_bucket(MINIO_BUCKET_NAME)
        except BucketAlreadyOwnedByYou:
            pass
        except BucketAlreadyExists:
            pass
        except ResponseError:
            raise

        try:
            return fn(*args, **kwargs)
        except ResponseError:
            raise

    return fn_inner


@with_minio
def put_file(filename, contents, contents_length=None):
    if not isinstance(contents, BytesIO):
        if isinstance(contents, str):
            contents = bytes(contents, encoding='utf-8')
            contents_length = len(contents)
        else:
            contents = bytes(contents)
        contents = BytesIO(contents)
        if not contents_length:
            contents.seek(SEEK_END)
            contents_length = contents.tell()
            contents.seek(SEEK_SET)
    return minioClient.put_object(MINIO_BUCKET_NAME, filename, contents,
                                  contents_length)


@with_minio
def get_file(filename):
    return minioClient.get_object(MINIO_BUCKET_NAME, filename).data


@with_minio
def list_files(**kwargs):
    return list(str(file_id.object_name) for file_id
                in minioClient.list_objects(MINIO_BUCKET_NAME, **kwargs))


def allowed_file(filename, allowed_extensions=None):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() \
           in (allowed_extensions or ALLOWED_EXTENSIONS)


def get_upload_form():
    return '''
    <!doctype html>
    <title>Upload new File</title>
    <h1>Upload new File</h1>
    <form method=post enctype=multipart/form-data>
      <p><input type="file" name="file[]" multiple="">
         <input type="submit" value="Upload">
    </form>
    '''


def get_task_status(task_id):
    task = result.AsyncResult(str(task_id))
    if isinstance(task.result, BaseException):
        task_result = str(task.result)
    else:
        task_result = task.result
    return {
        "task_id": str(task.id),
        "ready": task.ready(),
        "status": task.status,
        "result": task_result,
        "error": str(task.traceback)
    }


def save_file(upload_file):
    filename = UPLOAD_PREFIX + secure_filename(upload_file.filename)
    file_bytes = BytesIO()
    upload_file.save(file_bytes)
    file_size = file_bytes.tell()
    file_bytes.seek(SEEK_SET)
    put_file(filename, file_bytes, file_size)
    return {
        'file_id': filename,
        'file_size': file_size
    }


def add_processed_file(module_nickname,
                       processed_file_id,
                       contents,
                       extension=None):
    if not processed_file_id:
        processed_file_id = str(uuid4())
    if extension:
        filename = PROCESSED_PREFIX + module_nickname + processed_file_id + ("." + extension)
    else:
        filename = ""
    put_file(filename, contents)
    return filename


def get_process_data(file_ids_list):
    files_to_process = list_files(recursive=True,
                                  prefix=UPLOAD_PREFIX)
    if file_ids_list:
        files_to_process = [UPLOAD_PREFIX + file_id
                            for file_id in file_ids_list
                            if (UPLOAD_PREFIX + file_id)
                            in files_to_process]
    data_to_process = {
        file_id[len(UPLOAD_PREFIX):]: get_file(file_id)
        for file_id in files_to_process}
    return data_to_process
