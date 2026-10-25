"""ReportModule: REST-эндпоинты /api/reports/*."""
from flask import Blueprint, Response, g, jsonify, request

from ..errors import ApiError
from ..security import auth_required
from . import exporters, service

bp = Blueprint("reports", __name__, url_prefix="/api/reports")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@bp.get("")
@auth_required("admin", "manager")
def history():
    """GET /api/reports — история сформированных отчётов."""
    return jsonify(service.list_reports())


@bp.get("/<report_type>")
@auth_required()
def get_report(report_type):
    """GET /api/reports/<assignee|project|period>?format=json|xlsx|pdf&..."""
    fmt = request.args.get("format", "json")
    if fmt not in ("json", "xlsx", "pdf"):
        raise ApiError(400, "invalid_format", "format: json, xlsx или pdf")
    report = service.build_report(g.current_user, report_type, request.args)
    if fmt == "xlsx":
        return Response(exporters.to_xlsx(report), mimetype=XLSX_MIME, headers={
            "Content-Disposition": f"attachment; filename=report_{report_type}.xlsx"})
    if fmt == "pdf":
        return Response(exporters.to_pdf(report), mimetype="application/pdf", headers={
            "Content-Disposition": f"attachment; filename=report_{report_type}.pdf"})
    return jsonify(report)
