from pyspark.sql import SparkSession
from pyspark.sql.functions import col, year, month, avg, max, lag, to_date, when
from pyspark.sql.window import Window
import boto3

# Inicialización de Spark
spark = SparkSession.builder.appName("MonthlyTemperatureAnalysis").getOrCreate()

# Parámetros de entrada y salida
input_path = "s3://summaryfiles-virginia/filtered/validFiles.csv"
output_path = "s3://summaryfiles-virginia/analysis/"
final_file_name = "analizedfiles.csv"
bucket_name = "summaryfiles-virginia"

# Se lee el archivo CSV como un DataFrame
data = spark.read.option("header", "true").option("inferSchema", "true").csv(input_path)

# Conversión de la columna Fecha al formato correcto
data = data.withColumn("Fecha", to_date(col("Fecha"), "yyyy/MM/dd"))

# Extraer Año y Mes de la columna Fecha
data = data.withColumn("Ano", year(col("Fecha"))) \
           .withColumn("Mes", month(col("Fecha")))

# Temperatura media mensual
avg_temp_monthly = data.groupBy("Ano", "Mes") \
    .agg(avg(col("Medias")).alias("TempMediaMensual"))

# Temperatura máxima mensual
max_temp_monthly = data.groupBy("Ano", "Mes") \
    .agg(max(col("Medias")).alias("TempMaxMensual"))

# Desviación máxima mensual
max_sd_monthly = data.groupBy("Ano", "Mes") \
    .agg(max(col("Desviaciones")).alias("MaxDesviacion"))

# Unión de métricas (media, máxima temperatura y máxima desviación) en un solo DataFrame
combined_metrics = avg_temp_monthly \
    .join(max_temp_monthly, ["Ano", "Mes"]) \
    .join(max_sd_monthly, ["Ano", "Mes"])

# Ventana de ordenación por Año y Mes consecutivamente
window_spec = Window.orderBy("Ano", "Mes")

# Diferencia de temperatura máxima respecto al mes anterior
result = combined_metrics.withColumn(
    "DiferenciaTempMax",
    when(lag("TempMaxMensual").over(window_spec).isNull(), None)
    .otherwise(col("TempMaxMensual") - lag("TempMaxMensual").over(window_spec))
)

# Reemplazar NULL con 0 para evitar errores al escribir (no dejaba convertir "" a float)
result = result.fillna({"DiferenciaTempMax": 0.0})

# COMPROBACIONES
print("Resultados calculados (listos para guardar):")
result.show()

# Unión a archivo único
temp_output_path = output_path + "temp/"
result.coalesce(1).write.mode("overwrite").csv(temp_output_path, header=True)

# Renombrar el archivo consolidado
s3_client = boto3.client('s3')
response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="analysis/temp/")

for obj in response.get('Contents', []):
    if obj['Key'].endswith('.csv'):
        copy_source = {'Bucket': bucket_name, 'Key': obj['Key']}
        s3_client.copy_object(Bucket=bucket_name, CopySource=copy_source, Key=f"analysis/{final_file_name}")
        s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])

print(f"Archivo consolidado guardado como {final_file_name} en s3://{bucket_name}/analysis/")
