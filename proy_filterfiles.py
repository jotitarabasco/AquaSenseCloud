import csv
import json
import urllib.parse
import boto3
from io import StringIO
from datetime import datetime

# Conexión al cliente S3 y SNS
s3_client = boto3.client('s3')
sns_client = boto3.client('sns')

# Buckets y archivos de entrada/salida
input_bucket = 'landingzone-virginia'
output_bucket = 'summaryfiles-virginia'
output_valid_key = 'filtered/validFiles.csv'
output_invalid_key = 'filtered/errorFiles.csv'
alert_topic_name = 'SD_LIMIT'  # Nombre del tema SNS para alertas

def lambda_handler(event, context):
    print("Evento recibido por Lambda: " + json.dumps(event, indent=2))

    # Bucket y clave del objeto
    source_bucket = event['Records'][0]['s3']['bucket']['name']
    object_key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])

    try:
        # Descargar el archivo CSV del landing zone
        response = s3_client.get_object(Bucket=source_bucket, Key=object_key)
        file_content = response['Body'].read().decode('utf-8')

        csv_reader = csv.reader(StringIO(file_content), delimiter=",")
        # Leer encabezados
        headers = next(csv_reader)
        assert headers == ['Fecha', 'Medias', 'Desviaciones'], "Encabezados incorrectos o formato inesperado."

        rows = list(csv_reader)

        # Separar registros válidos de los erróneos
        valid_rows = []
        invalid_rows = []

        for row in rows:
            try:
                # Extraer datos de cada columna
                fecha, media, sd = row[0].strip(), row[1].strip(), row[2].strip()

                # Validar datos faltantes
                assert fecha.strip(), "Fecha faltante en el registro."
                assert media.strip(), "Media faltante en el registro."
                assert sd.strip(), "Desviación típica faltante en el registro."

                # Estandarizar el formato de fecha
                fecha_dt = datetime.strptime(fecha, "%Y/%m/%d")  # Intenta convertir directamente
                fecha_estandar = fecha_dt.strftime("%Y/%m/%d")  # Formato estandarizado

                # Validar rango de fecha
                assert fecha_dt <= datetime.now(), "La fecha supera la fecha actual."
                assert fecha_dt >= datetime(2017, 1, 1), "La fecha está fuera del rango permitido (2017-año actual)."

                # Validar valores de Media y SD
                media_val = float(media)
                sd_val = float(sd)
                assert media_val >= 0, "La media es negativa."
                assert sd_val >= 0, "La desviación típica es negativa."

                # Enviar alerta si la desviación típica supera 0.5
                if sd_val > 0.5:
                    send_sns_alert(fecha_estandar, sd)

                # Agregar registro válido con la fecha estandarizada
                valid_rows.append([fecha_estandar, media, sd])

            except Exception as e:
                # Agregar registro inválido
                invalid_rows.append(row)
                print(f"Error en fila {row}: {str(e)}")

        # Procesar y guardar registros válidos e inválidos
        process_csv(output_bucket, output_valid_key, valid_rows, ['Fecha', 'Medias', 'Desviaciones'])
        process_csv(output_bucket, output_invalid_key, invalid_rows, ['Fecha', 'Medias', 'Desviaciones'])

        print(f"Procesamiento completo. {len(valid_rows)} registros válidos, {len(invalid_rows)} registros inválidos.")

        return {
            'statusCode': 200,
            'body': json.dumps('Archivo procesado con éxito.')
        }

    except Exception as e:
        print(f"Error procesando el archivo {object_key}: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }


def send_sns_alert(fecha, sd):
    """
    Enviar alerta a SNS si la desviación típica supera 0.5.
    """
    try:
        # Construir el mensaje
        message = f"Alerta: Desviación típica de {sd} detectada el {fecha}. Verifique los datos."
        print(f"Enviando alerta SNS: {message}")

        # Obtener el ARN del tema SNS
        sns_topic_arn = [
            t['TopicArn'] for t in sns_client.list_topics()['Topics']
            if t['TopicArn'].lower().endswith(f":{alert_topic_name.lower()}")
        ][0]

        # Publicar el mensaje en SNS
        sns_client.publish(
            TopicArn=sns_topic_arn,
            Message=message,
            Subject='Alerta de Desviación Típica',
            MessageStructure='raw'
        )
        print(f"Alerta SNS enviada al tema {alert_topic_name}.")

    except Exception as e:
        print(f"Error al enviar la alerta SNS: {str(e)}")


def process_csv(bucket, key, new_rows, headers):
    """
    Crear o actualizar un archivo CSV en S3, asegurando que no existan filas duplicadas.
    Si una fila con la misma fecha ya existe, actualiza los valores de Media y Desviación.
    """
    try:
        # Intentar obtener el archivo existente
        response = s3_client.get_object(Bucket=bucket, Key=key)
        csv_content = response['Body'].read().decode('utf-8')
        csv_reader = csv.reader(StringIO(csv_content))
        existing_rows = list(csv_reader)
    except s3_client.exceptions.NoSuchKey:
        # Si el archivo no existe, crear uno nuevo con encabezados
        print(f"{key} no encontrado. Creando un nuevo archivo.")
        existing_rows = [headers]

    # Crear un diccionario para manejar duplicados basado en la columna "Fecha"
    rows_dict = {row[0]: row for row in existing_rows[1:]}  # Excluir encabezados

    for new_row in new_rows:
        fecha = new_row[0]
        if fecha in rows_dict:
            # Actualizar valores de Media y Desviación si ya existe la fecha
            rows_dict[fecha][1] = new_row[1]  # Actualizar Media
            rows_dict[fecha][2] = new_row[2]  # Actualizar Desviación
        else:
            # Agregar nueva fila si no existe la fecha
            rows_dict[fecha] = new_row

    # Reconstruir filas actualizadas, incluyendo encabezados
    updated_rows = [headers] + list(rows_dict.values())

    # Subir el archivo actualizado a S3
    csv_buffer = StringIO()
    csv_writer = csv.writer(csv_buffer, delimiter=',', quoting=csv.QUOTE_MINIMAL)
    csv_writer.writerows(updated_rows)

    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=csv_buffer.getvalue(),
        ContentType='text/csv'
    )
    print(f"Archivo actualizado subido a {bucket}/{key}")
