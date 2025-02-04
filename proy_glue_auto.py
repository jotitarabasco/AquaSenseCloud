import boto3
import json

def lambda_handler(event, context):
    glue_client = boto3.client('glue')

    # Nombre del Glue Job
    glue_job_name = 'agregated_values'

    try:
        # Iniciar el Glue Job
        response = glue_client.start_job_run(JobName=glue_job_name)
        print(f"Glue Job {glue_job_name} iniciado con éxito. JobRunID: {response['JobRunId']}")

        return {
            'statusCode': 200,
            'body': json.dumps(f"Glue Job {glue_job_name} iniciado con éxito.")
        }
    except Exception as e:
        print(f"Error al iniciar el Glue Job: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error al iniciar el Glue Job: {str(e)}")
        }
