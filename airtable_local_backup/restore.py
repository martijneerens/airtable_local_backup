"""Handle restoring items to airtable databases."""
import base64
import lzma
import hashlib
import airtable
import boto3
from airtable_local_backup import exceptions
from airtable_local_backup import common


def decode_file(item, check_integrity=True):
    """
    Decodes filedata store in backup dumps.

    Arguments:
        item: the file data to decode
        check_integrity: bool- flag whether to check the resulting data against
        the stored hash.

    Returns: dict: {'filename': name of the file, 'data': (bytes)decoded data}
    This data could be used as:
        with open(return['filename'], 'wb') as outfile:
            outfile.write(return['data']

    Raises DataCorruptionError if integrity check fails.
    """
    filedata = base64.b64decode(item['data'])
    if item['compressed']:
        body = lzma.decompress(filedata)
    else:
        body = filedata
    if check_itegrity:
        bodyhash = hashlib.md5(filedata).hexdigest()
        if not bodyhash == item['md5hash']:
            raise exceptions.DataCorruptionError(
                'file: {} failed the data integrity check, '
                'and may be corrupted.')
    return {'filename': item['filename'], 'data': filedata}


def upload_attachment(item, bucket, prefix=''):
    """
    Uploads a file for attachment to airtable record.

    Arguments:
        item: dict from decode_file containing decoded file info
        bucket: the s3 bucket for uploading attachments temporarily.
        prefix: the prefix to append to objects uploaded to s3 (include slash
        if it should look like a folder).

    Returns: presigned url for the temporary object to pass to airtable for
    download.
    """
    s3client = boto3.client('s3')
    filename = prefix + item['filename']
    # TODO: investigate sending md5 hash along to aws
    upload = s3client.put_object(Bucket=bucket,
                                 Key=filename,
                                 Body=item['data'],
                                 ServerSideEncryption='AES256')
    return s3client.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': bucket,
            'Key': filename
        }
    )


def read_data(table_data, attach_info=None):
    """
    Reads table data from input stream and yields records for insertion into
    airtable.

    Arguments:
        table_data: a json object generated by DownloadTable
        attach_info: a dict of:
                        bucket: s3 bucket to upload attachments to temporarily
                        prefix: the prefix for those objects
                        check_itegrity: bool whether to run hash to check
                        data integrity
    Yields: a generator of json objects for uploading to airtable with s3
    endpoints for attachments if specified.
    """
    for record in table_data:
        newdata = {}
        # print(record)
        for key, value in record.items():
            if list(common._findkeys(value, 'filename')):
                urls = []
                if not attach_info:
                    continue
                for item in value:
                    filedata = decode_file(
                        item, check_integrity=attach_info['check_itegrity'])
                    url = upload_attachment(item=filedata,
                                            bucket=attach_info['s3'],
                                            prefix=attach_info['prefix'],
                                            )
                    urls.append({'url': url})
                newdata[key] = urls
            else:
                newdata[key] = value

        yield newdata
