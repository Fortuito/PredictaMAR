from flask import Flask, send_file, render_template_string, request
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "demo"


HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>PredictaMAR Demo</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f4f7fb;
            margin: 0;
            padding: 40px;
        }

        .container {
            max-width: 750px;
            margin: auto;
            background: white;
            padding: 35px;
            border-radius: 14px;
            box-shadow: 0 4px 18px rgba(0,0,0,0.08);
        }

        h1 {
            margin-top: 0;
        }

        .status {
            background: #eef8f0;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
        }

        select {
            padding: 10px;
            width: 100%;
            margin-top: 8px;
            margin-bottom: 20px;
        }

        .download {
            display: inline-block;
            padding: 12px 22px;
            background: #0066cc;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: bold;
        }

        .empty {
            color: #b00020;
        }
    </style>
</head>

<body>

<div class="container">

    <h1>PredictaMAR</h1>

    <p>Histórico local de datos ambientales.</p>

    {% if archivos %}

        <div class="status">
            ✓ Datos disponibles
        </div>

        <form method="GET">

            <label>
                <strong>Seleccionar versión:</strong>
            </label>

            <select
                name="archivo"
                onchange="this.form.submit()"
            >

                {% for item in archivos %}
                    <option
                        value="{{ item.nombre }}"
                        {% if item.nombre == seleccionado %}
                            selected
                        {% endif %}
                    >
                        {{ item.fecha }} - {{ item.nombre }}
                    </option>
                {% endfor %}

            </select>

        </form>

        <p>
            <strong>Archivo seleccionado:</strong><br>
            {{ seleccionado }}
        </p>

        <a
            class="download"
            href="/download/{{ seleccionado }}"
        >
            Descargar JSON
        </a>

    {% else %}

        <div class="empty">
            No hay archivos JSON disponibles.
        </div>

    {% endif %}

</div>

</body>
</html>
"""


def listar_archivos():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    archivos = sorted(
        DATA_DIR.glob("*.json"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    resultado = []

    for archivo in archivos:

        fecha = datetime.fromtimestamp(
            archivo.stat().st_mtime
        ).strftime("%d/%m/%Y %H:%M:%S")

        resultado.append({
            "nombre": archivo.name,
            "fecha": fecha
        })

    return resultado


@app.route("/")
def home():

    archivos = listar_archivos()

    if not archivos:
        return render_template_string(
            HTML,
            archivos=[]
        )

    seleccionado = request.args.get(
        "archivo",
        archivos[0]["nombre"]
    )

    nombres = [
        x["nombre"]
        for x in archivos
    ]

    if seleccionado not in nombres:
        seleccionado = archivos[0]["nombre"]

    return render_template_string(
        HTML,
        archivos=archivos,
        seleccionado=seleccionado
    )


@app.route("/download/<filename>")
def download(filename):

    archivo = DATA_DIR / filename

    if not archivo.exists():
        return "Archivo no encontrado", 404

    return send_file(
        archivo,
        as_attachment=True,
        download_name=archivo.name
    )


if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )