import os
import cv2
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename

aplicacion = Flask(__name__)
aplicacion.secret_key = 'clave_secreta_super_segura' # Necesario para mostrar mensajes (flash)
aplicacion.config['CARPETA_SUBIDAS'] = 'static/uploads'
aplicacion.config['TAMANO_MAXIMO'] = 16 * 1024 * 1024 # Límite máximo de 16 MB

# Asegurarse de que la carpeta de subidas exista
os.makedirs(aplicacion.config['CARPETA_SUBIDAS'], exist_ok=True)

EXTENSIONES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'bmp'}

def archivo_permitido(nombre_archivo):
    return '.' in nombre_archivo and nombre_archivo.rsplit('.', 1)[1].lower() in EXTENSIONES_PERMITIDAS

def procesar_suavizado(ruta_imagen, ruta_salida):
    """
    Aplica un filtro promedio de 3x3 usando operaciones explícitas de numpy para simular una ventana móvil.
    (Versión optimizada y vectorizada para que funcione rápido)
    """
    img = cv2.imread(ruta_imagen)
    if img is None:
        return False

    # Obtener dimensiones
    alto, ancho, canales = img.shape
    
    # Añadir un borde de 1 píxel a la imagen original para manejar los bordes (reflejando los bordes)
    img_con_borde = cv2.copyMakeBorder(img, 1, 1, 1, 1, cv2.BORDER_REFLECT)
    img_con_borde = img_con_borde.astype(np.float32)

    # Crear una imagen de salida del mismo tamaño, llena de ceros
    img_salida = np.zeros_like(img, dtype=np.float32)
    
    # Aplicar el promedio con ventana de 3x3 sumando las sub-matrices desplazadas
    for i in range(-1, 2):
        for j in range(-1, 2):
            img_salida += img_con_borde[1+i:alto+1+i, 1+j:ancho+1+j]
            
    img_salida /= 9.0
            
    # Convertir de vuelta a uint8
    img_salida = np.uint8(img_salida)
    cv2.imwrite(ruta_salida, img_salida)
    return True

@aplicacion.route('/')
def inicio():
    return render_template('index.html')

@aplicacion.route('/clasificacion', methods=['GET', 'POST'])
def clasificacion():
    if request.method == 'POST':
        if 'archivo' not in request.files:
            flash('No se encontró el archivo')
            return redirect(request.url)
        archivo = request.files['archivo']
        if archivo.filename == '':
            flash('No se seleccionó ningún archivo')
            return redirect(request.url)
        if archivo and archivo_permitido(archivo.filename):
            nombre_archivo = secure_filename(archivo.filename)
            ruta_entrada = os.path.join(aplicacion.config['CARPETA_SUBIDAS'], 'in_clas_' + nombre_archivo)
            archivo.save(ruta_entrada)
            
            # Solo guardamos la imagen y la mostramos. La clasificación se hará al hacer clic.
            return render_template('clasificacion.html', imagen_cargada='in_clas_' + nombre_archivo)

    return render_template('clasificacion.html')

@aplicacion.route('/clasificar_pixel', methods=['POST'])
def clasificar_pixel():
    datos = request.json
    x = int(datos.get('x', 0))
    y = int(datos.get('y', 0))
    nombre_imagen = datos.get('imagen', '')
    
    ruta_imagen = os.path.join(aplicacion.config['CARPETA_SUBIDAS'], nombre_imagen)
    img = cv2.imread(ruta_imagen)
    
    if img is None:
        return jsonify({'error': 'Imagen no encontrada'}), 400

    # Extraer una pequeña vecindad (ventana de 5x5) para ser más robustos
    alto_img, ancho_img, _ = img.shape
    y_min = max(0, y - 2)
    y_max = min(alto_img, y + 3)
    x_min = max(0, x - 2)
    x_max = min(ancho_img, x + 3)
    
    try:
        ventana = img[y_min:y_max, x_min:x_max]
        promedio_bgr = np.mean(ventana, axis=(0, 1))
    except Exception:
        return jsonify({'error': 'Coordenadas fuera de rango'}), 400

    # Convertir el promedio BGR a RGB para mostrar en la interfaz
    r = int(promedio_bgr[2])
    g = int(promedio_bgr[1])
    b = int(promedio_bgr[0])

    # Convertir a HSV para hacer una clasificación más robusta a la iluminación
    pixel_promedio_bgr = np.uint8([[promedio_bgr]])
    pixel_hsv = cv2.cvtColor(pixel_promedio_bgr, cv2.COLOR_BGR2HSV)[0][0]
    
    h, s, v = pixel_hsv[0], pixel_hsv[1], pixel_hsv[2]

    # Árbol de decisiones basado en HSV (Hue, Saturation, Value)
    # Valores en OpenCV: H (0-179), S (0-255), V (0-255)
    if v < 50:
        clase_detectada = "Asfalto / Sombra"
    elif s < 45 and v > 190:
        clase_detectada = "Nubes / Nieve / Blanco"
    elif s < 50 and v <= 190:
        clase_detectada = "Cemento / Roca"
    else:
        # Tiene suficiente color, evaluamos el Tono (Hue)
        if (h >= 0 and h < 22) or (h >= 165):
            clase_detectada = "Tierra Húmeda / Ladrillo"
        elif h >= 22 and h < 38:
            clase_detectada = "Tierra Seca / Arena"
        elif h >= 38 and h < 85:
            clase_detectada = "Césped / Vegetación"
        elif h >= 85 and h < 110:
            if v > 160:
                clase_detectada = "Cielo Despejado"
            else:
                clase_detectada = "Agua (Lago / Río)"
        elif h >= 110 and h < 135:
            clase_detectada = "Agua Profunda / Océano"
        else:
            clase_detectada = "Superficie Artificial"

    return jsonify({
        'clase': clase_detectada,
        'color_rgb': f'rgb({r}, {g}, {b})'
    })


@aplicacion.route('/suavizado', methods=['GET', 'POST'])
def suavizado():
    if request.method == 'POST':
        if 'archivo' not in request.files:
            flash('No se encontró el archivo')
            return redirect(request.url)
        archivo = request.files['archivo']
        if archivo.filename == '':
            flash('No se seleccionó ningún archivo')
            return redirect(request.url)
        if archivo and archivo_permitido(archivo.filename):
            nombre_archivo = secure_filename(archivo.filename)
            ruta_entrada = os.path.join(aplicacion.config['CARPETA_SUBIDAS'], 'in_suav_' + nombre_archivo)
            nombre_salida = 'out_suav_' + nombre_archivo
            ruta_salida = os.path.join(aplicacion.config['CARPETA_SUBIDAS'], nombre_salida)
            
            archivo.save(ruta_entrada)
            
            if procesar_suavizado(ruta_entrada, ruta_salida):
                return render_template('suavizado.html', 
                                       imagen_entrada='in_suav_' + nombre_archivo,
                                       imagen_salida=nombre_salida)
            else:
                flash('Error al procesar la imagen')
                return redirect(request.url)

    return render_template('suavizado.html')

@aplicacion.route('/vaca_lola')
def vaca_lola():
    return render_template('vaca_lola.html')

if __name__ == '__main__':
    aplicacion.run(debug=True)
