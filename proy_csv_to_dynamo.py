import csv
import json
import boto3
import urllib.parse
from io import StringIO
from decimal import Decimal

# Conexión S3 y DynamoDB
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Nombre de la tabla DynamoDB
dynamo_table_name = "TemperatureData"

def lambda_handler(event, context):
    print("Evento recibido por Lambda: " + json.dumps(event, indent=2))

    # Obtener bucket y objeto del evento
    source_bucket = event['Records'][0]['s3']['bucket']['name']
    object_key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])

    try:
        # Descarga del archivo CSV desde S3
        response = s3_client.get_object(Bucket=source_bucket, Key=object_key)
        file_content = response['Body'].read().decode('utf-8')

        # Lectura del contenido del CSV
        csv_reader = csv.DictReader(StringIO(file_content))

        # Conexión DynamoDB
        table = dynamodb.Table(dynamo_table_name)

        # Procesar cada fila del CSV y escribir en DynamoDB
        for row in csv_reader:
            try:
                # Formateo de datos para DynamoDB
                item = {
                    "Ano": int(row["Ano"]),  # Clave primaria (Año)
                    "Mes": int(row["Mes"]),  # Clave de rango (Mes)
                    "TempMediaMensual": Decimal(row["TempMediaMensual"]),
                    "TempMaxMensual": Decimal(row["TempMaxMensual"]),
                    "DiferenciaTempMax": Decimal(row["DiferenciaTempMax"]),
                    "MaxDesviacion": Decimal(row["MaxDesviacion"]),  # Nueva columna
                }

                # Inserción de elementos en DynamoDB
                table.put_item(Item=item)
                print(f"Fila insertada en DynamoDB: {item}")

            except Exception as e:
                print(f"Error procesando la fila: {row}. Error: {str(e)}")

        return {
            'statusCode': 200,
            'body': json.dumps('Archivo CSV procesado e importado a DynamoDB con éxito.')
        }

    except Exception as e:
        print(f"Error procesando el archivo {object_key}: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }