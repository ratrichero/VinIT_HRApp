from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from app.core.exceptions import HRAException
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.api import api_router
from app.services.langfuse_observability import shutdown as shutdown_langfuse
from app.workers.processor import worker

# Setup logging first
setup_logging()
logger = get_logger(__name__)


def _clamav_state() -> str:
    """Trả `connected` / `unavailable` / `disabled` — **không** ném lỗi.

    `disabled` nghĩa là chưa cấu hình socket (chủ ý), khác với `unavailable`
    nghĩa là đã cấu hình nhưng clamd không trả lời. Gộp hai thứ này làm một thì
    không phân biệt được "chưa bật tính năng" với "hỏng".

    Chỉ mở socket rồi đóng, không gửi dữ liệu: health probe phải rẻ và không được
    đẩy tệp qua clamd. `scan_bytes` không dùng được ở đây vì nó cần dữ liệu để
    quét; nhưng tiêu chí kết nối thì giống — cùng một đường Unix socket.
    """
    socket_path = settings.CLAMAV_UNIX_SOCKET
    if not socket_path.startswith("/"):
        return "disabled"
    import socket as _socket
    try:
        with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as conn:
            conn.settimeout(2.0)
            conn.connect(socket_path)
        return "connected"
    except OSError as exc:
        logger.warning("ClamAV readiness probe failed", error_type=type(exc).__name__)
        return "unavailable"


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="VinUniversity AI-Native CV Matching & Ranking Platform API",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HRAException)
    async def handle_hra_error(request: Request, exc: HRAException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        # Pydantic/FastAPI validation details can echo the submitted body,
        # including passwords and setup tokens. Never return those to callers.
        #
        # Nhưng nuốt TẤT CẢ thành một câu chung chung là lỗi khác, và đã gây hại
        # thật: rule nghiệp vụ viết trong ``@model_validator`` (ví dụ "Tiêu chí
        # số năm cần min_years") cũng bị thay bằng "Dữ liệu gửi đi không hợp lệ.",
        # nên HR bấm Lưu, thấy câu đó, và không biết phải sửa ô nào.
        #
        # Phân biệt hai loại:
        # * lỗi do chính mình viết trong validator (``value_error``): câu thông
        #   báo là văn bản ta kiểm soát, không chứa dữ liệu người dùng → trả về.
        # * lỗi kiểu/định dạng của Pydantic (``type_error``, ``string_too_long``…):
        #   chúng hay kèm giá trị đã gửi → vẫn trả câu chung.
        messages = []
        for error in exc.errors():
            if error.get("type") == "value_error":
                message = str(error.get("msg", "")).replace("Value error, ", "").strip()
                if message and message not in messages:
                    messages.append(message)
        if messages:
            return JSONResponse(status_code=422, content={"detail": "; ".join(messages)})
        return JSONResponse(status_code=422, content={"detail": "Dữ liệu gửi đi không hợp lệ."})

    # Include API routers
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health", tags=["Health Check"])
    async def health_check():
        """Liveness probe - returns immediately without checking downstream dependencies."""
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "environment": settings.APP_ENV
        }

    @app.get("/health/ready", tags=["Health Check"])
    async def readiness_check():
        """Readiness probe - verifies database connectivity, reports scanner state.

        ClamAV được **báo cáo**, không được dùng để chặn 503. Lý do: máy quét
        chết thì đường nhận CV hỏng (`careers_intake.py` fail-closed), nhưng phần
        lớn hệ thống — xem vị trí, chấm hồ sơ đã nhận, duyệt rubric — vẫn chạy
        bình thường. Trả 503 sẽ khiến load balancer rút backend khỏi vòng phục vụ
        và biến "thiếu máy quét" thành "sập toàn hệ thống".

        Trước đây endpoint này không nhắc gì tới máy quét, nên `clamav` chết vẫn
        báo `ready` — không có tín hiệu nào cho giám sát. Đó là lỗi im lặng mà
        mục HANG-01/HANG-03 đã ghi nhận.

        Ai muốn siết thì bật `READINESS_REQUIRE_CLAMAV`; khi cờ đó bật **và** máy
        quét không sẵn sàng thì mới trả 503.
        """
        from sqlalchemy import text
        from app.db.database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as exc:
            logger.error("Database readiness check failed", error_type=type(exc).__name__)
            return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "unavailable"})
        finally:
            db.close()
        clamav_status = _clamav_state()
        payload = {
            "status": "ready",
            "database": db_status,
            "clamav": clamav_status,
            "app": settings.APP_NAME,
            "environment": settings.APP_ENV,
        }
        if settings.READINESS_REQUIRE_CLAMAV and clamav_status != "connected":
            return JSONResponse(status_code=503, content={**payload, "status": "unhealthy"})
        return payload

    @app.on_event("startup")
    async def startup_event():
        logger.info(
            "Starting VinUni HRA Backend",
            environment=settings.APP_ENV,
            debug=settings.DEBUG
        )
        # Start background processing worker
        if settings.APP_ENV != "testing":
            worker.start()
            logger.info("Background processing worker started automatically")

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Shutting down VinUni HRA Backend")
        worker.stop()
        shutdown_langfuse()

    return app


app = create_app()
