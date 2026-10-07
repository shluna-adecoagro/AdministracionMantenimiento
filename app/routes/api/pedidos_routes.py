from flask import Blueprint, request, jsonify
from app.services.pedidos_service import crear_pedido
from app.utils.json_validator import JsonSchemaValidator

pedidos_bp = Blueprint("pedidos", __name__)

validator = JsonSchemaValidator(
    "schemas/pedidos/pedido_input.schema.json"
)


@pedidos_bp.route("/pedidos", methods=["POST"])
def crear():
    data = request.get_json()

    if not data:
        return jsonify({"error": "JSON vacío o inválido"}), 400

    try:
        # 👇 VALIDACIÓN FORMAL
        validator.validar(data)

        pedido = crear_pedido(data)
        return jsonify({
            "mensaje": "Pedido creado correctamente",
            "pedido_id": pedido.PedidoID
        }), 201

    except ValueError as e:
        # Errores de validación o negocio
        return jsonify({"error": str(e)}), 400

    except Exception as e:
        print("ERROR INTERNO >>>", repr(e))
        import traceback
        traceback.print_exc()

        return jsonify({
            "error": "Error interno del servidor",
            "detalle": str(e)
        }), 500
