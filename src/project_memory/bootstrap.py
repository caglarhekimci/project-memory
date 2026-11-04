from datetime import UTC, datetime

from project_memory.application.ingestion import Ingestor
from project_memory.domain.models import SourceInput
from project_memory.domain.ports import MemoryStore

DEMO_SOURCES = [
    (
        "StockLedger",
        "caglarhekimci/stockledger-go",
        ("CI", "Docker validation"),
        [
            (
                "Redis ve veri bütünlüğü",
                "Redis yalnızca hız sınırlama amacıyla kullanılır. Stok ve rezervasyon "
                "kayıtlarının asıl kaynağı PostgreSQL'dir. Stok değişikliği ile outbox olayı "
                "aynı veritabanı işlemi içinde yazılır. Kafka olayları en az bir kez teslim "
                "edilir; tüketiciler olay kimliğiyle tekrarları ayırt etmelidir.",
            ),
            (
                "Idempotency kararı",
                "Idempotency anahtarı aynı işlemin tekrar gönderilmesini güvenli hale getirir. "
                "Aynı anahtar ve aynı içerik önceki rezervasyonu döndürür. Aynı anahtar farklı "
                "bir içerikle kullanılırsa 409 çakışma yanıtı verilir. "
                "Anahtarlar proje kiracısına göre ayrılır.",
            ),
            (
                "Docker bildirimi · kayıtlı örnek",
                "3 Kasım 2026 tarihli geliştirme kaydında, eski Docker denemesi Compose YAML "
                "yazım hatası nedeniyle başarısız olmuştu. Sonraki düzeltmede veritabanı "
                "bağlantı ayarları düzenlendi. Bu belge geçmiş bir örnektir; mevcut dalın test "
                "durumunu kanıtlamaz. Güncel durum için GitHub kontrollerini yenileyin.",
            ),
        ],
    ),
    (
        "ProcureFlow",
        "caglarhekimci/procureflow-next",
        ("Validate", "Docker validation"),
        [
            (
                "Onay ve yetkilendirme",
                "Satın alma talebini oluşturan kişi kendi talebini onaylayamaz. Requester "
                "talep oluşturur, approver onaylar veya reddeder, viewer kayıtları görüntüler. "
                "Taleplerin ve sorguların tenant sınırı korunur.",
            ),
            (
                "SQLite ve kalıcılık",
                "ProcureFlow verileri SQLite üzerinde tutulur. Para tutarları tam sayı olarak "
                "kaydedilir. İşlem geçmişi aynı işlem içinde yazılır. Docker named volume "
                "kullanımı konteyner değiştirilirken kayıtları ve oturumları korumayı amaçlar; "
                "güncel test sonucu ayrıca sorgulanmalıdır.",
            ),
        ],
    ),
]


def seed_demo(store: MemoryStore) -> None:
    if store.projects():
        return
    for name, repository, workflows, documents in DEMO_SOURCES:
        project = store.create_project(name, repository, workflows)
        for index, (title, body) in enumerate(documents):
            source = SourceInput(
                f"demo:{index}",
                title,
                body,
                "",
                "recorded-example-2026-11-03",
                datetime(2026, 11, 3, tzinfo=UTC),
                "demo",
            )
            Ingestor(store).ingest(project.id, source)
