import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, ForeignKey, 
    Numeric, Text, UniqueConstraint, Index, Enum, func
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class IngestionLifecycleState(str, enum.Enum):
    PENDING = 'PENDING'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    SKIPPED = 'SKIPPED'

class RawSchemaMixin:
    __table_args__ = {'schema': 'raw'}

class ControlSchemaMixin:
    __table_args__ = {'schema': 'control'}

class Fund(RawSchemaMixin, Base):
    __tablename__ = 'funds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    provider = Column(String(255), nullable=False)

    holdings = relationship('Holding', back_populates='fund', cascade='all, delete-orphan')
    sector_allocations = relationship('FundSectorAllocation', back_populates='fund', cascade='all, delete-orphan')
    fund_history = relationship('FundHistory', back_populates='fund', cascade='all, delete-orphan')
    fund_performance = relationship('FundPerformance', back_populates='fund', cascade='all, delete-orphan')

class Sector(RawSchemaMixin, Base):
    __tablename__ = 'sectors'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sector_name = Column(String(100), unique=True, nullable=False)

    assets = relationship('Asset', back_populates='sector')
    fund_sector_allocations = relationship('FundSectorAllocation', back_populates='sector')

class Asset(RawSchemaMixin, Base):
    __tablename__ = 'assets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    sector_id = Column(Integer, ForeignKey('raw.sectors.id'), nullable=True)
    market_cap = Column(Numeric(20, 2), nullable=True)

    sector = relationship('Sector', back_populates='assets')
    holdings = relationship('Holding', back_populates='asset')
    prices = relationship('AssetPrice', back_populates='asset')

class Holding(RawSchemaMixin, Base):
    __tablename__ = 'holdings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey('raw.funds.id'), nullable=False)
    asset_id = Column(Integer, ForeignKey('raw.assets.id'), nullable=False)
    weight = Column(Numeric(10, 6), nullable=False)
    date = Column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint('fund_id', 'asset_id', 'date', name='uix_fund_asset_date'),
        Index('idx_holdings_fund_id_date', 'fund_id', 'date'),
        Index('idx_holdings_date', 'date'),
        {'schema': 'raw'},
    )
    
    fund = relationship('Fund', back_populates='holdings')
    asset = relationship('Asset', back_populates='holdings')

class FundSectorAllocation(RawSchemaMixin, Base):
    __tablename__ = 'fund_sector_allocation'

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey('raw.funds.id'), nullable=False)
    sector_id = Column(Integer, ForeignKey('raw.sectors.id'), nullable=False)
    allocation = Column(Numeric(10, 6), nullable=False)
    date = Column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint('fund_id', 'sector_id', 'date', name='uix_fund_sector_date'),
        Index('idx_fsa_fund_sector_date', 'fund_id', 'sector_id', 'date'),
        {'schema': 'raw'},
    )

    fund = relationship('Fund', back_populates='sector_allocations')
    sector = relationship('Sector', back_populates='fund_sector_allocations')

class FundHistory(RawSchemaMixin, Base):
    __tablename__ = 'fund_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey('raw.funds.id'), nullable=False)
    change_description = Column(Text, nullable=False)
    date = Column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint('fund_id', 'date', name='uix_fund_history'),
        Index('idx_fh_fund_id_date', 'fund_id', 'date'),
        {'schema': 'raw'},
    )

    fund = relationship('Fund', back_populates='fund_history')

class AssetPrice(RawSchemaMixin, Base):
    __tablename__ = 'asset_price'

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey('raw.assets.id'), nullable=False)
    price = Column(Numeric(12, 4), nullable=False)
    date = Column(Date, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('asset_id', 'date', name='uix_asset_price_date'),
        Index('idx_ap_asset_id_date', 'asset_id', 'date'),
        {'schema': 'raw'},
    )

    asset = relationship('Asset', back_populates='prices')

class FundPerformance(RawSchemaMixin, Base):
    __tablename__ = 'fund_performance'

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey('raw.funds.id'), nullable=False)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Numeric(12, 6), nullable=False)
    date = Column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint('fund_id', 'metric_name', 'date', name='uix_performance_metric_date'),
        Index('idx_fp_fund_id_date', 'fund_id', 'date'),
        {'schema': 'raw'}
    )

    fund = relationship('Fund', back_populates='fund_performance')

class ETLLog(ControlSchemaMixin, Base):
    __tablename__ = 'etl_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(DateTime, nullable=False, server_default=func.now())
    status = Column(String(50), nullable=False)
    message = Column(Text)

class IngestedFiles(ControlSchemaMixin, Base):
    __tablename__ = 'ingested_files'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    quarter_id = Column(String(10), nullable=False, unique=True)
    file_url = Column(String(512), nullable=False)
    local_path = Column(String(255))
    
    lifecycle_state = Column(
        Enum(IngestionLifecycleState, native_enum=False),
        nullable=False,
        default=IngestionLifecycleState.PENDING
    )
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    files_downloaded = Column(Integer, default=0)
    holdings_extracted = Column(Integer, default=0)
    xml_parse_errors = Column(Integer, default=0)
    
    error_message = Column(Text)
    error_traceback = Column(Text)
    retry_count = Column(Integer, default=0)
    
    __table_args__ = (
        Index('idx_ingested_files_quarter_id', 'quarter_id'),
        Index('idx_ingested_files_lifecycle_state', 'lifecycle_state'),
        {'schema': 'control'},
    )

class SourceMetaData(ControlSchemaMixin, Base):
    __tablename__ = 'source_metadata'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(255), nullable=False)
    url = Column(String(255))
    last_updated = Column(Date)