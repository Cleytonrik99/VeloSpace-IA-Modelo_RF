from flask import Flask, request, jsonify
import pickle
import pandas as pd

MODEL_PATH = "modelo_rf.pkl"

# Colunas usadas para treinar o modelo.
# Mantenha a mesma ordem usada no treinamento.
FEATURE_COLUMNS = [
    "height",
    "width",
    "length",
    "weight",
    "measured_height",
    "measured_width",
    "measured_length",
    "measured_weight",
    "capacity_height",
    "capacity_width",
    "capacity_length",
    "capacity_weight",
    "satellite_priority_id",
    "satellite_status_id",
    "rocket_status_id",
    "height_difference",
    "width_difference",
    "length_difference",
    "weight_difference",
    "height_margin",
    "width_margin",
    "length_margin",
    "weight_margin"
]

with open(MODEL_PATH, "rb") as f:
    modelo = pickle.load(f)

app = Flask(__name__)


def normalize_input(data):
    """
    Aceita dois formatos:
    1) Um único objeto JSON:
       { "height": 10, "width": 10, ... }

    2) Uma lista de objetos JSON:
       [
         { "height": 10, "width": 10, ... },
         { "height": 12, "width": 11, ... }
       ]
    """
    if isinstance(data, dict):
        return pd.DataFrame([data])

    if isinstance(data, list):
        return pd.DataFrame(data)

    raise ValueError("O JSON enviado deve ser um objeto ou uma lista de objetos.")


def create_calculated_columns(df):
    """
    Cria automaticamente as colunas calculadas caso elas não sejam enviadas no JSON.
    """

    required_base_columns = [
        "height",
        "width",
        "length",
        "weight",
        "measured_height",
        "measured_width",
        "measured_length",
        "measured_weight",
        "capacity_height",
        "capacity_width",
        "capacity_length",
        "capacity_weight"
    ]

    missing_base = [col for col in required_base_columns if col not in df.columns]

    if missing_base:
        raise ValueError(f"Campos obrigatórios ausentes para cálculo: {missing_base}")

    df["height_difference"] = df["measured_height"] - df["height"]
    df["width_difference"] = df["measured_width"] - df["width"]
    df["length_difference"] = df["measured_length"] - df["length"]
    df["weight_difference"] = df["measured_weight"] - df["weight"]

    df["height_margin"] = df["capacity_height"] - df["measured_height"]
    df["width_margin"] = df["capacity_width"] - df["measured_width"]
    df["length_margin"] = df["capacity_length"] - df["measured_length"]
    df["weight_margin"] = df["capacity_weight"] - df["measured_weight"]

    return df


def validate_columns(df):
    missing = [col for col in FEATURE_COLUMNS if col not in df.columns]

    if missing:
        raise ValueError(f"Campos obrigatórios ausentes: {missing}")

    return df[FEATURE_COLUMNS]


def define_risk_level(approval_probability):
    if approval_probability >= 0.75:
        return "LOW"
    if approval_probability >= 0.50:
        return "MEDIUM"
    return "HIGH"


def define_main_reason(row, prediction):
    if prediction == "A":
        return "O satélite está dentro das dimensões e peso suportados pelo foguete."

    if row["height_margin"] < 0:
        return "A altura medida ultrapassa a capacidade de altura do foguete."

    if row["width_margin"] < 0:
        return "A largura medida ultrapassa a capacidade de largura do foguete."

    if row["length_margin"] < 0:
        return "O comprimento medido ultrapassa a capacidade de comprimento do foguete."

    if row["weight_margin"] < 0:
        return "O peso medido ultrapassa a capacidade de peso do foguete."

    if (
        abs(row["height_difference"]) > 3 or
        abs(row["width_difference"]) > 3 or
        abs(row["length_difference"]) > 4 or
        abs(row["weight_difference"]) > 4
    ):
        return "As medidas da inspeção apresentam diferença relevante em relação ao cadastro."

    if row["rocket_status_id"] != 1:
        return "O status do foguete pode indicar indisponibilidade ou restrição."

    if row["satellite_status_id"] != 1:
        return "O status do satélite pode indicar pendência ou inconsistência."

    return "O modelo identificou risco com base no conjunto de dados técnicos."


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "VeloSpace ML API está online.",
        "endpoint": "/predict",
        "method": "POST"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model_loaded": modelo is not None
    })


@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json()

        if data is None:
            return jsonify({
                "erro": "Nenhum JSON foi enviado."
            }), 400

        df_original = normalize_input(data)
        df = df_original.copy()

        df = create_calculated_columns(df)
        X = validate_columns(df)

        predictions = modelo.predict(X)

        probabilities = None
        classes = None

        if hasattr(modelo, "predict_proba"):
            probabilities = modelo.predict_proba(X)
            classes = list(modelo.classes_)

        response = []

        for index, prediction in enumerate(predictions):
            prediction = str(prediction)

            approval_probability = None

            if probabilities is not None and "A" in classes:
                approved_index = classes.index("A")
                approval_probability = round(float(probabilities[index][approved_index]), 4)

            if approval_probability is not None:
                risk_level = define_risk_level(approval_probability)
            else:
                risk_level = "LOW" if prediction == "A" else "HIGH"

            response.append({
                "prediction": prediction,
                "prediction_label": "APPROVED" if prediction == "A" else "REJECTED",
                "approval_probability": approval_probability,
                "risk_level": risk_level,
                "main_reason": define_main_reason(df.iloc[index], prediction)
            })

        return jsonify({
            "total_predictions": len(response),
            "results": response
        })

    except ValueError as e:
        return jsonify({
            "erro": str(e)
        }), 400

    except Exception as e:
        return jsonify({
            "erro": "Erro interno ao realizar a predição.",
            "detalhes": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
