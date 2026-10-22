from pathlib import Path
import sqlite3
import random
import json
from datetime import date, timedelta
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parent
DATA = ROOT
OUT = ROOT
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
AS_OF = '2026-10-21'

def database(tables):
    conn = sqlite3.connect(ROOT / 'analysis.sqlite')
    # Rebuild in reverse dependency order. Foreign keys stay enabled for inserts.
    conn.execute('PRAGMA foreign_keys = OFF')
    for name in reversed(list(tables)):
        conn.execute(f'DROP TABLE IF EXISTS "{name}"')
    conn.executescript((ROOT / 'schema.sql').read_text())
    conn.execute('PRAGMA foreign_keys = ON')
    for name, frame in tables.items():
        frame.to_csv(DATA / f'{name}.csv', index=False)
        frame.to_sql(name, conn, if_exists='append', index=False)
    violations = conn.execute('PRAGMA foreign_key_check').fetchall()
    assert not violations, violations
    return conn

def queries(conn):
    # Every block starts with -- name: <output_name> and contains one SQL statement.
    text = (ROOT / 'analysis.sql').read_text()
    results = {}
    for block in text.split('-- name: ')[1:]:
        name, sql = block.split('\n', 1)
        frame = pd.read_sql_query(sql.strip(), conn, params={'as_of': AS_OF})
        results[name.strip()] = frame
        frame.to_csv(OUT / f'{name.strip()}.csv', index=False)
    return results

def parity(actual, expected, key, columns):
    a = actual.sort_values(key)[columns].reset_index(drop=True)
    b = expected.sort_values(key)[columns].reset_index(drop=True)
    assert_frame_equal(a, b, check_dtype=False, check_exact=False, atol=1e-7, rtol=1e-7)

def chart(frame, x, y, title, ylabel):
    plt.rcParams.update({'font.size': 10})
    fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
    ax.bar(frame[x].astype(str), frame[y], color='#24658b')
    ax.set(title=title, ylabel=ylabel)
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(axis='x', rotation=30)
    fig.savefig(OUT / 'summary.png', dpi=160)
    plt.close(fig)

def finish(text, checks):
    (OUT / 'findings.md').write_text(text, encoding='utf-8')
    (OUT / 'validation.json').write_text(json.dumps({'status': 'passed', 'checks': checks}, indent=2) + '\n')
    print(text)

def main():
    rng=random.Random(202)
    customers=pd.DataFrame([{'customer_id':i,'region':['North','South','East','West'][i%4]} for i in range(1,151)])
    products=pd.DataFrame([{'sku':f'P{i:03}','category':['Essentials','Premium','Accessories'][i%3]} for i in range(1,301)])
    rows=[]
    for i in range(1,9001):
        cost=rng.randint(10000,300000)
        price=int(cost*rng.uniform(1.1,1.8))
        if i%41==0: price=int(cost*0.8)
        rows.append({'line_id':i,'customer_id':rng.randint(1,150),'sku':f'P{rng.randint(1,300):03}',
                     'sale_date':str(date.fromisoformat(AS_OF)-timedelta(days=rng.randint(0,172))),
                     'units':rng.randint(1,12),'unit_price_paise':price,'unit_cost_paise':cost})
    raw=pd.DataFrame(rows)
    raw=pd.concat([raw,raw.iloc[[0]]],ignore_index=True)
    raw.loc[15,'units']=0
    raw.to_csv(DATA/'transactions_raw.csv',index=False)
    duplicate=raw.duplicated('line_id',keep='first')
    bad_units=raw.units<=0
    rejects=raw[duplicate|bad_units].copy()
    rejects['reason']=['duplicate line ID' if duplicate.loc[i] else 'non-positive units' for i in rejects.index]
    rejects.to_csv(OUT/'quarantine.csv',index=False)
    sales=raw[~(duplicate|bad_units)].copy()
    conn=database({'customers':customers,'products':products,'transactions':sales})
    result=queries(conn)
    calc=sales.merge(products,on='sku')
    calc['revenue_inr']=calc.units*calc.unit_price_paise/100
    calc['cost_inr']=calc.units*calc.unit_cost_paise/100
    calc['gross_margin_inr']=calc.revenue_inr-calc.cost_inr
    expected=calc.groupby('category')[['revenue_inr','cost_inr','gross_margin_inr']].sum().reset_index()
    expected['gross_margin_pct']=100*expected.gross_margin_inr/expected.revenue_inr
    parity(result['category_margin'],expected,'category',['category','revenue_inr','cost_inr','gross_margin_inr','gross_margin_pct'])
    calc['month']=calc.sale_date.str[:7]
    monthly=calc.groupby('month').revenue_inr.sum().reset_index()
    monthly['prior_revenue_inr']=monthly.revenue_inr.shift(1)
    monthly['change_pct']=(monthly.revenue_inr/monthly.prior_revenue_inr-1)*100
    monthly['cumulative_revenue_inr']=monthly.revenue_inr.cumsum()
    parity(result['monthly_revenue'],monthly,'month',['month','revenue_inr','prior_revenue_inr','change_pct','cumulative_revenue_inr'])
    totals=calc.groupby('customer_id').revenue_inr.sum().reset_index()
    parity(result['customer_concentration'],totals,'customer_id',['customer_id','revenue_inr'])
    assert len(rejects)==2 and len(sales)==8999
    assert abs(result['customer_concentration'].revenue_share_pct.sum()-100)<1e-8
    assert len(result['below_cost_lines'])==len(calc[calc.unit_price_paise<calc.unit_cost_paise])
    assert abs(calc.revenue_inr.sum()-calc.cost_inr.sum()-calc.gross_margin_inr.sum())<1e-6
    chart(result['category_margin'],'category','gross_margin_pct','Weighted gross margin by category | synthetic data','Gross margin percent')
    top5=result['customer_concentration'].head(5).revenue_share_pct.sum()
    finish(f"# Commercial findings\n\nThrough {AS_OF}; synthetic demonstration.\n\n"
           f"- Analysed {len(sales):,} valid transaction lines; quarantined {len(rejects)} source defects.\n"
           f"- Revenue: INR {calc.revenue_inr.sum():,.2f}; gross margin: INR {calc.gross_margin_inr.sum():,.2f} "
           f"({calc.gross_margin_inr.sum()/calc.revenue_inr.sum():.1%}).\n"
           f"- {len(result['below_cost_lines']):,} below-cost lines need review; top five customers contribute {top5:.1f}% of revenue.\n\n"
           "## Recommended action\nReview below-cost lines against approved promotions and cost records. "
           "Use weighted category margins with sales mix, and monitor customer concentration.\n\n"
           "## Limits\nGross margin excludes overheads, freight, taxes, returns and credits. "
           "Price is realised unit price after any discount; cost is recorded transaction cost. "
           "May and October are partial months: monthly changes are descriptive, not like-for-like growth. "
           "Below-cost gaps are exceptions for investigation, not verified avoidable losses. No forecast is claimed.\n",
           ['SQL/Pandas category, monthly and customer parity','revenue minus cost reconciles to gross margin',
            'customer shares sum to 100%','invalid rows quarantined','below-cost count reconciles','foreign keys checked'])
    conn.close()

if __name__ == '__main__':
    main()
