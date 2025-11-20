from sqlalchemy import(
    Column, Integer, String, Float, Date, ForeignKey, Numeric, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()

# Schema mixin to apply default schema (all tables) inheritance
class RawSchemaMixin:
    __table_args__ = {'schema': 'raw'}

class ControlSchemaMixin:
    __table_args__= {'schema': 'control'}

# Note: Pay attention to foreign keys across all classes.
class Fund(RawSchemaMixin, Base):
    __tablename__ = 'funds'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    provider = Column(String(255), nullable=False)

    holdings = relationship('Holding', back_populates='fund')
    sector_allocations = relationship('FundSectorAllocation', back_populates='fund')
    fund_history = relationship('FundHistory', back_populates='fund')
    fund_performance = relationship('FundPerformance', back_populates='fund')

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
    sector_id = Column(Integer, ForeignKey('raw.sectors.id'))
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

    __table_args__= (
        UniqueConstraint('fund_id', 'asset_id', 'date', name='uix_fund_asset_date'),
        Index('idx_holdings_fund_id_date', 'fund_id', 'date'),
        Index('idx_holdings_date_brin', 'date', postgresql_using='brin'),
        {'schema': 'raw'},
    )
    
    fund = relationship('Fund', back_populates='holdings')
    asset = relationship('Asset', back_populates='holdings')

# Note that allocation is set to float and not integer, due to allocation % for the sector
class FundSectorAllocation(RawSchemaMixin, Base):
    __tablename__ = 'fund_sector_allocation'
    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey('raw.funds.id'), nullable=False)
    sector_id = Column(Integer, ForeignKey('raw.sectors.id'), nullable=False)
    allocation = Column(Numeric(10, 6), nullable=False)
    date = Column(Date, nullable=False)

    __table_args__= (
        UniqueConstraint('fund_id', 'sector_id', 'date', name='uix_fund_sector_date'),
        Index('idx_fsa_fund_sector_date', 'fund_id', 'sector_id', 'date'),
        Index('idx_fsa_date_brin', 'date', postgresql_using='brin'),
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

    __table_args__= (
        UniqueConstraint('fund_id', 'date', name='uix_fund_history'),
        Index('idx_fh_fund_id_date', 'fund_id', 'date'),
        Index('idx_fh_date_brin', 'date', postgresql_using='brin'),
        {'schema': 'raw'},
    )

    fund = relationship('Fund', back_populates='fund_history')

# Status here with the string 50 is either success or failed
class ETLLog(ControlSchemaMixin, Base):
    __tablename__ = 'etl_log'
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False)
    status = Column(String(50), nullable=False)
    message = Column(Text)


class SourceMetaData(ControlSchemaMixin, Base):
    __tablename__= 'source_metadata'
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(255), nullable=False)
    url = Column(String(255))
    last_updated = Column(Date)


class AssetPrice(RawSchemaMixin, Base):
    __tablename__ = 'asset_price'
    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey('raw.assets.id'), nullable=False)
    price = Column(Numeric(12, 4), nullable=False)
    date = Column(Date, nullable=False)
    
    __table_args__= (
        UniqueConstraint('asset_id', 'date', name='uix_asset_price_date'),
        Index('idx_ap_asset_id_date', 'asset_id', 'date'),
        Index('idx_ap_date_brin', 'date', postgresql_using='brin'),
        {'schema': 'raw'},
    )

    asset = relationship('Asset', back_populates='prices')


class FundPerformance(RawSchemaMixin, Base):
    __tablename__='fund_performance'
    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(Integer, ForeignKey('raw.funds.id'), nullable=False)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Numeric(12, 6), nullable=False)
    date = Column(Date, nullable=False)

    __table_args__= (
        UniqueConstraint('fund_id', 'metric_name', 'date', name='uix_performance_metric_date'),
        Index('idx_fp_fund_id_date', 'fund_id', 'date'),
        Index('idx_fp_date_brin', 'date', postgresql_using='brin'),
        {'schema': 'raw'}
    )

    fund = relationship('Fund', back_populates='fund_performance')

    # note: 'relationship()' allows (orm style e.g. symbiotic accesss between related objects)