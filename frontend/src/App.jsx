import React, { useState, useEffect, useMemo } from 'react';
import {
  LayoutDashboard,
  Boxes,
  TrendingUp,
  ShoppingCart,
  Truck,
  AlertTriangle,
  RefreshCw,
  Search,
  Bell,
  CheckCircle2,
  AlertCircle,
  ArrowUpRight,
  ChevronRight,
  ShieldAlert,
  Layers,
  Building2,
  DollarSign,
  PackageCheck,
  Check,
  Filter,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';

const API_BASE = 'http://localhost:8000';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [stock, setStock] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [selectedWarehouse, setSelectedWarehouse] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [loading, setLoading] = useState(false);
  const [runningPipeline, setRunningPipeline] = useState(false);
  const [feedback, setFeedback] = useState(null); // { type: 'success' | 'error', message: '' }

  // Forecast state
  const [forecastProduct, setForecastProduct] = useState('');
  const [forecastWarehouse, setForecastWarehouse] = useState('');
  const [chartData, setChartData] = useState([]);
  const [forecastLoading, setForecastLoading] = useState(false);

  // Forms
  const [saleForm, setSaleForm] = useState({
    customer_id: '',
    warehouse_id: '',
    payment_method: 'card',
    product_id: '',
    quantity: 1,
    unit_price: 0,
    discount: 0,
  });

  const [poForm, setPoForm] = useState({
    po_id: '',
    warehouse_id: '',
    product_id: '',
    quantity: 10,
    unit_cost: 0,
  });

  // Load initial dropdowns
  useEffect(() => {
    fetch(`${API_BASE}/products`).then(r => r.json()).then(data => {
      setProducts(data);
      if (data.length > 0) setForecastProduct(String(data[0].product_id));
    }).catch(console.error);

    fetch(`${API_BASE}/warehouses`).then(r => r.json()).then(data => {
      setWarehouses(data);
      if (data.length > 0) setForecastWarehouse(String(data[0].warehouse_id));
    }).catch(console.error);

    fetch(`${API_BASE}/customers`).then(r => r.json()).then(setCustomers).catch(console.error);
    fetch(`${API_BASE}/purchase-orders`).then(r => r.json()).then(setPurchaseOrders).catch(console.error);
  }, []);

  // Fetch stock and alerts
  const loadData = () => {
    setLoading(true);
    let url = `${API_BASE}/stock-levels?low_stock_only=${lowStockOnly}`;
    if (selectedWarehouse) url += `&warehouse_id=${selectedWarehouse}`;

    Promise.all([
      fetch(url).then(r => r.json()),
      fetch(`${API_BASE}/alerts`).then(r => r.json()),
    ])
      .then(([stockData, alertData]) => {
        setStock(Array.isArray(stockData) ? stockData : []);
        setAlerts(Array.isArray(alertData) ? alertData : []);
        setLoading(false);
      })
      .catch(err => {
        setFeedback({ type: 'error', message: err.message });
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, [selectedWarehouse, lowStockOnly]);

  // Load forecast chart whenever product or warehouse changes
  useEffect(() => {
    if (!forecastProduct || !forecastWarehouse) return;
    setForecastLoading(true);

    Promise.all([
      fetch(`${API_BASE}/forecasts/history?product_id=${forecastProduct}&warehouse_id=${forecastWarehouse}`).then(r => r.json()),
      fetch(`${API_BASE}/forecasts?product_id=${forecastProduct}&warehouse_id=${forecastWarehouse}`).then(r => r.json()),
    ])
      .then(([history, forecasts]) => {
        const histData = Array.isArray(history) ? history.slice(-21).map(h => ({
          date: h.sale_date.slice(5),
          actual: Number(h.daily_qty),
        })) : [];

        const predData = Array.isArray(forecasts) ? forecasts.slice(0, 21).map(f => ({
          date: f.forecast_date.slice(5),
          predicted: Number(f.predicted_demand),
        })) : [];

        setChartData([...histData, ...predData]);
        setForecastLoading(false);
      })
      .catch(() => setForecastLoading(false));
  }, [forecastProduct, forecastWarehouse]);

  // Trigger Forecast Pipeline
  const handleRunPipeline = () => {
    setRunningPipeline(true);
    setFeedback(null);
    fetch(`${API_BASE}/forecasts/run`, { method: 'POST' })
      .then(async r => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'Pipeline run failed');
        return data;
      })
      .then(data => {
        setFeedback({
          type: 'success',
          message: `Forecasting completed! Generated ${data.forecasts_written} daily predictions & raised ${data.alerts_generated} automated reorder alerts.`,
        });
        loadData();
        setRunningPipeline(false);
      })
      .catch(err => {
        setFeedback({ type: 'error', message: err.message });
        setRunningPipeline(false);
      });
  };

  // Update Alert Status
  const handleUpdateAlert = (alertId, newStatus) => {
    fetch(`${API_BASE}/alerts/${alertId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    })
      .then(r => r.json())
      .then(() => {
        setFeedback({ type: 'success', message: `Alert #${alertId} updated to ${newStatus}` });
        loadData();
      })
      .catch(err => setFeedback({ type: 'error', message: err.message }));
  };

  // Submit Sale
  const handleSaleSubmit = (e) => {
    e.preventDefault();
    setFeedback(null);
    const body = {
      customer_id: Number(saleForm.customer_id),
      warehouse_id: Number(saleForm.warehouse_id),
      payment_method: saleForm.payment_method,
      items: [{
        product_id: Number(saleForm.product_id),
        quantity: Number(saleForm.quantity),
        unit_price: Number(saleForm.unit_price),
        discount: Number(saleForm.discount || 0),
      }],
    };

    fetch(`${API_BASE}/sales`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(async r => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'Sale processing failed');
        return data;
      })
      .then(data => {
        setFeedback({
          type: 'success',
          message: `Sale #${data.sale_id} completed successfully! Stock deducted atomically via database stored procedure.`,
        });
        loadData();
      })
      .catch(err => setFeedback({ type: 'error', message: err.message }));
  };

  // Submit PO
  const handlePoSubmit = (e) => {
    e.preventDefault();
    setFeedback(null);
    const body = {
      po_id: Number(poForm.po_id),
      warehouse_id: Number(poForm.warehouse_id),
      items: [{
        product_id: Number(poForm.product_id),
        quantity: Number(poForm.quantity),
        unit_cost: Number(poForm.unit_cost),
      }],
    };

    fetch(`${API_BASE}/purchase-orders/receive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(async r => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || 'PO receiving failed');
        return data;
      })
      .then(data => {
        setFeedback({
          type: 'success',
          message: `Received ${data.items_received} units for Purchase Order #${data.po_id}. Stock levels updated.`,
        });
        loadData();
      })
      .catch(err => setFeedback({ type: 'error', message: err.message }));
  };

  // KPI Calculations
  const stats = useMemo(() => {
    const totalValuation = stock.reduce((sum, item) => sum + (Number(item.quantity_on_hand) * Number(item.unit_price || 0)), 0);
    const totalUnits = stock.reduce((sum, item) => sum + Number(item.quantity_on_hand), 0);
    const lowStockItems = stock.filter(item => Number(item.available_qty) <= Number(item.reorder_point));
    const outOfStockItems = stock.filter(item => Number(item.available_qty) <= 0);
    const openAlerts = alerts.filter(a => a.status === 'open');

    return {
      totalValuation: totalValuation.toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }),
      totalUnits: totalUnits.toLocaleString(),
      lowStockCount: lowStockItems.length,
      outOfStockCount: outOfStockItems.length,
      openAlertsCount: openAlerts.length,
    };
  }, [stock, alerts]);

  // Filtered Stock for Search
  const filteredStock = useMemo(() => {
    if (!searchQuery.trim()) return stock;
    const q = searchQuery.toLowerCase();
    return stock.filter(s =>
      s.product_name.toLowerCase().includes(q) ||
      s.sku.toLowerCase().includes(q) ||
      s.warehouse_name.toLowerCase().includes(q)
    );
  }, [stock, searchQuery]);

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: '#f8fafc' }}>
      {/* ─── SIDEBAR NAVIGATION ───────────────────────────── */}
      <aside style={{
        width: 260,
        backgroundColor: '#0f172a',
        color: '#f8fafc',
        display: 'flex',
        flexDirection: 'column',
        position: 'sticky',
        top: 0,
        height: '100vh',
        borderRight: '1px solid #1e293b',
        zIndex: 50,
      }}>
        {/* Brand Header */}
        <div style={{ padding: '24px 20px', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 38,
            height: 38,
            borderRadius: 10,
            background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(37, 99, 235, 0.4)',
          }}>
            <Boxes size={22} color="#ffffff" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 17, letterSpacing: '-0.3px', color: '#ffffff' }}>StockSense</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }}></span>
              <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 500 }}>v2.4.1 — LIVE</span>
            </div>
          </div>
        </div>

        {/* Navigation Items */}
        <nav style={{ padding: '20px 12px', flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {[
            { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
            { id: 'inventory', label: 'Inventory / Catalog', icon: Boxes },
            { id: 'forecast', label: 'Demand Forecasting', icon: TrendingUp },
            { id: 'sales', label: 'Sales Orders', icon: ShoppingCart },
            { id: 'purchase_orders', label: 'Purchase Orders', icon: Truck },
            { id: 'alerts', label: 'Reorder Alerts', icon: AlertTriangle, badge: stats.openAlertsCount },
          ].map(item => {
            const Icon = item.icon;
            const active = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => { setActiveTab(item.id); setFeedback(null); }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  width: '100%',
                  padding: '10px 14px',
                  borderRadius: 8,
                  border: 'none',
                  background: active ? '#2563eb' : 'transparent',
                  color: active ? '#ffffff' : '#94a3b8',
                  fontSize: 13.5,
                  fontWeight: active ? 600 : 500,
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                }}
              >
                <Icon size={18} color={active ? '#ffffff' : '#94a3b8'} />
                <span style={{ flex: 1 }}>{item.label}</span>
                {item.badge > 0 && (
                  <span style={{
                    backgroundColor: active ? '#ffffff' : '#ef4444',
                    color: active ? '#2563eb' : '#ffffff',
                    fontSize: 11,
                    fontWeight: 700,
                    padding: '2px 7px',
                    borderRadius: 999,
                  }}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Sidebar Footer User Info */}
        <div style={{ padding: '16px 20px', borderTop: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            backgroundColor: '#334155',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: 14,
            color: '#e2e8f0',
          }}>
            OP
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#f8fafc', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Operations Lead</div>
            <div style={{ fontSize: 11, color: '#64748b' }}>Admin Workspace</div>
          </div>
        </div>
      </aside>

      {/* ─── MAIN CONTENT CONTAINER ────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Top Header */}
        <header style={{
          height: 64,
          backgroundColor: '#ffffff',
          borderBottom: '1px solid #e2e8f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 28px',
          position: 'sticky',
          top: 0,
          zIndex: 40,
        }}>
          {/* Global Search */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, maxWidth: 440 }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              width: '100%',
              backgroundColor: '#f1f5f9',
              padding: '8px 12px',
              borderRadius: 8,
              border: '1px solid #e2e8f0',
            }}>
              <Search size={16} color="#64748b" />
              <input
                type="text"
                placeholder="Search SKUs, products, warehouses..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                style={{
                  border: 'none',
                  background: 'transparent',
                  outline: 'none',
                  fontSize: 13,
                  width: '100%',
                  color: '#0f172a',
                }}
              />
              <kbd style={{
                fontSize: 10,
                backgroundColor: '#ffffff',
                border: '1px solid #cbd5e1',
                padding: '2px 5px',
                borderRadius: 4,
                color: '#64748b',
                fontWeight: 600,
              }}>Ctrl+K</kbd>
            </div>
          </div>

          {/* Top Actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            {/* Warehouse Selector */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#475569' }}>
              <Building2 size={16} color="#64748b" />
              <select
                value={selectedWarehouse}
                onChange={e => setSelectedWarehouse(e.target.value)}
                style={{
                  padding: '7px 10px',
                  borderRadius: 6,
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  fontSize: 13,
                  color: '#0f172a',
                  fontWeight: 500,
                }}
              >
                <option value="">All Warehouses</option>
                {warehouses.map(w => (
                  <option key={w.warehouse_id} value={w.warehouse_id}>{w.warehouse_name} ({w.location})</option>
                ))}
              </select>
            </div>

            {/* Run Forecast CTA Button */}
            <button
              onClick={handleRunPipeline}
              disabled={runningPipeline}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                backgroundColor: '#2563eb',
                color: '#ffffff',
                border: 'none',
                padding: '8px 16px',
                borderRadius: 6,
                fontWeight: 600,
                fontSize: 13,
                cursor: runningPipeline ? 'not-allowed' : 'pointer',
                boxShadow: '0 2px 4px rgba(37, 99, 235, 0.25)',
              }}
            >
              <RefreshCw size={14} className={runningPipeline ? 'spin' : ''} />
              {runningPipeline ? 'Calculating...' : 'Run Forecast Pipeline'}
            </button>
          </div>
        </header>

        {/* Main View Area */}
        <main style={{ padding: '28px', maxWidth: 1400, width: '100%', margin: '0 auto' }}>
          {/* Feedback Banners */}
          {feedback && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '12px 16px',
              borderRadius: 8,
              marginBottom: 24,
              backgroundColor: feedback.type === 'success' ? '#f0fdf4' : '#fef2f2',
              color: feedback.type === 'success' ? '#166534' : '#991b1b',
              border: `1px solid ${feedback.type === 'success' ? '#bbf7d0' : '#fecaca'}`,
              fontSize: 13.5,
              fontWeight: 500,
            }}>
              {feedback.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
              <span>{feedback.message}</span>
            </div>
          )}

          {/* ════════════════════ VIEW 1: DASHBOARD ════════════════════ */}
          {activeTab === 'dashboard' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              {/* Header Title */}
              <div>
                <h1 style={{ fontSize: 22, fontWeight: 700, color: '#0f172a' }}>Inventory Overview & Demand Forecast</h1>
                <p style={{ fontSize: 13.5, color: '#64748b', marginTop: 2 }}>
                  Real-time stock velocity, statistical reorder safety thresholds, and 30-day proactive forecasts.
                </p>
              </div>

              {/* 4 KPI Summary Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
                {/* KPI 1 */}
                <div style={{ backgroundColor: '#ffffff', padding: 20, borderRadius: 10, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>Total Stock Valuation</span>
                    <span style={{ backgroundColor: '#eff6ff', padding: 6, borderRadius: 8 }}><DollarSign size={16} color="#2563eb" /></span>
                  </div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: '#0f172a', marginTop: 8 }}>{stats.totalValuation}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6, fontSize: 12, color: '#16a34a', fontWeight: 600 }}>
                    <ArrowUpRight size={14} /> +4.2% vs last month
                  </div>
                </div>

                {/* KPI 2 */}
                <div style={{ backgroundColor: '#ffffff', padding: 20, borderRadius: 10, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>Units on Hand</span>
                    <span style={{ backgroundColor: '#f0fdf4', padding: 6, borderRadius: 8 }}><PackageCheck size={16} color="#16a34a" /></span>
                  </div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: '#0f172a', marginTop: 8 }}>{stats.totalUnits} Units</div>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 6 }}>Across 30 active SKUs</div>
                </div>

                {/* KPI 3 */}
                <div style={{ backgroundColor: '#ffffff', padding: 20, borderRadius: 10, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>Low Stock Warnings</span>
                    <span style={{ backgroundColor: '#fffbeb', padding: 6, borderRadius: 8 }}><AlertTriangle size={16} color="#d97706" /></span>
                  </div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: '#d97706', marginTop: 8 }}>{stats.lowStockCount} SKUs</div>
                  <div style={{ fontSize: 12, color: '#b45309', marginTop: 6, fontWeight: 500 }}>Below dynamic reorder point</div>
                </div>

                {/* KPI 4 */}
                <div style={{ backgroundColor: '#ffffff', padding: 20, borderRadius: 10, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>Critical Reorder Alerts</span>
                    <span style={{ backgroundColor: '#fef2f2', padding: 6, borderRadius: 8 }}><ShieldAlert size={16} color="#dc2626" /></span>
                  </div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: '#dc2626', marginTop: 8 }}>{stats.openAlertsCount} Open</div>
                  <div style={{ fontSize: 12, color: '#b91c1c', marginTop: 6, fontWeight: 500 }}>Immediate action needed</div>
                </div>
              </div>

              {/* Demand Forecast Visualizer Card */}
              <div style={{ backgroundColor: '#ffffff', borderRadius: 10, border: '1px solid #e2e8f0', padding: '20px 24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
                  <div>
                    <h2 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a' }}>Demand Forecast vs. Actual Consumption</h2>
                    <p style={{ fontSize: 12.5, color: '#64748b' }}>Comparing recent historical sales against the winning model's 30-day projection</p>
                  </div>

                  <div style={{ display: 'flex', gap: 10 }}>
                    <select
                      value={forecastProduct}
                      onChange={e => setForecastProduct(e.target.value)}
                      style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13 }}
                    >
                      {products.map(p => (
                        <option key={p.product_id} value={p.product_id}>{p.sku} — {p.product_name}</option>
                      ))}
                    </select>

                    <select
                      value={forecastWarehouse}
                      onChange={e => setForecastWarehouse(e.target.value)}
                      style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13 }}
                    >
                      {warehouses.map(w => (
                        <option key={w.warehouse_id} value={w.warehouse_id}>{w.warehouse_name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {forecastLoading ? (
                  <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: 14 }}>
                    Loading time-series data...
                  </div>
                ) : chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={290}>
                    <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#e2e8f0' }} tickLine={false} />
                      <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#e2e8f0' }} tickLine={false} />
                      <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: 'none', borderRadius: 8, color: '#fff', fontSize: 12 }} />
                      <Legend wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
                      <Line type="monotone" dataKey="actual" stroke="#2563eb" strokeWidth={2.5} name="Actual Daily Sales" dot={false} />
                      <Line type="monotone" dataKey="predicted" stroke="#dc2626" strokeWidth={2.5} strokeDasharray="5 5" name="Predicted Demand (AI Model)" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: 14 }}>
                    No forecast data available for this selection. Click "Run Forecast Pipeline" above.
                  </div>
                )}
              </div>

              {/* Lower Split Grid: Low Stock Alert Feed + Recent Activity */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 20 }}>
                {/* Low Stock Focus */}
                <div style={{ backgroundColor: '#ffffff', borderRadius: 10, border: '1px solid #e2e8f0', padding: 20 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                    <h3 style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>Low Stock Inventory Priority</h3>
                    <button
                      onClick={() => setActiveTab('inventory')}
                      style={{ background: 'transparent', border: 'none', color: '#2563eb', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                    >
                      View All <ChevronRight size={14} />
                    </button>
                  </div>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #f1f5f9', textAlign: 'left', color: '#64748b' }}>
                        <th style={{ padding: '8px 4px' }}>SKU</th>
                        <th style={{ padding: '8px 4px' }}>Warehouse</th>
                        <th style={{ padding: '8px 4px', textAlign: 'right' }}>Available</th>
                        <th style={{ padding: '8px 4px', textAlign: 'right' }}>Reorder Pt</th>
                        <th style={{ padding: '8px 4px', textAlign: 'center' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stock.filter(s => s.available_qty <= s.reorder_point).slice(0, 5).map(item => (
                        <tr key={item.stock_id} style={{ borderBottom: '1px solid #f8fafc' }}>
                          <td style={{ padding: '10px 4px', fontWeight: 600 }}>{item.sku}</td>
                          <td style={{ padding: '10px 4px', color: '#64748b' }}>{item.warehouse_name}</td>
                          <td style={{ padding: '10px 4px', textAlign: 'right', fontWeight: 700, color: '#dc2626' }}>{item.available_qty}</td>
                          <td style={{ padding: '10px 4px', textAlign: 'right' }}>{item.reorder_point}</td>
                          <td style={{ padding: '10px 4px', textAlign: 'center' }}>
                            <span style={{ fontSize: 11, fontWeight: 700, backgroundColor: '#fef2f2', color: '#b91c1c', padding: '2px 8px', borderRadius: 999 }}>
                              REORDER
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Real-time Reorder Alerts */}
                <div style={{ backgroundColor: '#ffffff', borderRadius: 10, border: '1px solid #e2e8f0', padding: 20 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                    <h3 style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>Active Supplier Reorder Alerts</h3>
                    <button
                      onClick={() => setActiveTab('alerts')}
                      style={{ background: 'transparent', border: 'none', color: '#2563eb', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                    >
                      Manage <ChevronRight size={14} />
                    </button>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {alerts.slice(0, 4).map(alert => (
                      <div key={alert.alert_id} style={{
                        padding: '12px 14px',
                        borderRadius: 8,
                        backgroundColor: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>
                            {alert.product_name} ({alert.sku})
                          </div>
                          <div style={{ fontSize: 11.5, color: '#64748b', marginTop: 2 }}>
                            {alert.warehouse_name} · Order {alert.suggested_order_qty} units from {alert.supplier_name}
                          </div>
                        </div>
                        {alert.status === 'open' && (
                          <button
                            onClick={() => handleUpdateAlert(alert.alert_id, 'acknowledged')}
                            style={{
                              padding: '5px 10px',
                              backgroundColor: '#ffffff',
                              border: '1px solid #cbd5e1',
                              borderRadius: 6,
                              fontSize: 11,
                              fontWeight: 600,
                              cursor: 'pointer',
                            }}
                          >
                            Acknowledge
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ════════════════════ VIEW 2: INVENTORY / CATALOG ════════════════════ */}
          {activeTab === 'inventory' && (
            <div style={{ backgroundColor: '#ffffff', borderRadius: 10, border: '1px solid #e2e8f0', padding: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                  <h2 style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>Catalog & Warehouse Stock Levels</h2>
                  <p style={{ fontSize: 13, color: '#64748b' }}>Normalized 3NF inventory positions with dynamic safety thresholds</p>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer', fontWeight: 500, color: '#334155' }}>
                    <input
                      type="checkbox"
                      checked={lowStockOnly}
                      onChange={e => setLowStockOnly(e.target.checked)}
                      style={{ accentColor: '#2563eb' }}
                    />
                    Only show items needing reorder
                  </label>
                </div>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '2px solid #e2e8f0', textAlign: 'left', color: '#475569' }}>
                      <th style={{ padding: '10px 12px' }}>SKU</th>
                      <th style={{ padding: '10px 12px' }}>Product</th>
                      <th style={{ padding: '10px 12px' }}>Warehouse</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right' }}>On Hand</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right' }}>Reserved</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right' }}>Available</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right' }}>Dynamic ROP</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right' }}>Unit Price</th>
                      <th style={{ padding: '10px 12px', textAlign: 'center' }}>Health</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStock.map(s => {
                      const isLow = Number(s.available_qty) <= Number(s.reorder_point);
                      return (
                        <tr key={s.stock_id} style={{ borderBottom: '1px solid #f1f5f9', backgroundColor: isLow ? '#fef2f2' : 'transparent' }}>
                          <td style={{ padding: '12px', fontWeight: 600 }}>{s.sku}</td>
                          <td style={{ padding: '12px' }}>{s.product_name}</td>
                          <td style={{ padding: '12px', color: '#64748b' }}>{s.warehouse_name}</td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>{s.quantity_on_hand}</td>
                          <td style={{ padding: '12px', textAlign: 'right', color: '#64748b' }}>{s.reserved_qty}</td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: isLow ? '#dc2626' : '#16a34a' }}>
                            {s.available_qty}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: 500 }}>{s.reorder_point}</td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>₹{Number(s.unit_price).toFixed(2)}</td>
                          <td style={{ padding: '12px', textAlign: 'center' }}>
                            <span style={{
                              fontSize: 11,
                              fontWeight: 700,
                              padding: '3px 10px',
                              borderRadius: 999,
                              backgroundColor: isLow ? '#fee2e2' : '#dcfce7',
                              color: isLow ? '#991b1b' : '#166534',
                            }}>
                              {isLow ? 'LOW STOCK' : 'HEALTHY'}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ════════════════════ VIEW 3: DEMAND FORECASTING ════════════════════ */}
          {activeTab === 'forecast' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div style={{ backgroundColor: '#ffffff', borderRadius: 10, border: '1px solid #e2e8f0', padding: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                  <div>
                    <h2 style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>Time-Series Predictive Forecasting</h2>
                    <p style={{ fontSize: 13, color: '#64748b' }}>
                      Out-of-sample backtesting selects between 14-Day SMA and ARIMA(1,1,1) via Mean Absolute Error (MAE).
                    </p>
                  </div>
                  <button
                    onClick={handleRunPipeline}
                    disabled={runningPipeline}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      backgroundColor: '#2563eb',
                      color: '#ffffff',
                      border: 'none',
                      padding: '8px 16px',
                      borderRadius: 6,
                      fontWeight: 600,
                      fontSize: 13,
                      cursor: 'pointer',
                    }}
                  >
                    <RefreshCw size={14} className={runningPipeline ? 'spin' : ''} />
                    {runningPipeline ? 'Running Models...' : 'Re-run Evaluation'}
                  </button>
                </div>

                <div style={{ display: 'flex', gap: 14, marginBottom: 20 }}>
                  <select
                    value={forecastProduct}
                    onChange={e => setForecastProduct(e.target.value)}
                    style={{ padding: '8px 14px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13, minWidth: 260 }}
                  >
                    {products.map(p => (
                      <option key={p.product_id} value={p.product_id}>{p.sku} — {p.product_name}</option>
                    ))}
                  </select>

                  <select
                    value={forecastWarehouse}
                    onChange={e => setForecastWarehouse(e.target.value)}
                    style={{ padding: '8px 14px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13, minWidth: 220 }}
                  >
                    {warehouses.map(w => (
                      <option key={w.warehouse_id} value={w.warehouse_id}>{w.warehouse_name}</option>
                    ))}
                  </select>
                </div>

                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#e2e8f0' }} />
                    <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={{ stroke: '#e2e8f0' }} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: 'none', borderRadius: 8, color: '#fff', fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
                    <Line type="monotone" dataKey="actual" stroke="#2563eb" strokeWidth={2.5} name="Actual Daily Demand" dot={false} />
                    <Line type="monotone" dataKey="predicted" stroke="#dc2626" strokeWidth={2.5} strokeDasharray="5 5" name="Predicted Demand" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Viva Explanation Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
                <div style={{ backgroundColor: '#ffffff', padding: 20, borderRadius: 10, border: '1px solid #e2e8f0' }}>
                  <h4 style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>1. 14-Day Moving Average</h4>
                  <p style={{ fontSize: 12.5, color: '#64748b', marginTop: 6, lineHeight: 1.5 }}>
                    Zero-parameter, non-parametric smoothing. Prevents overfitting on low-count, intermittent retail sales histories.
                  </p>
                </div>
                <div style={{ backgroundColor: '#ffffff', padding: 20, borderRadius: 10, border: '1px solid #e2e8f0' }}>
                  <h4 style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>2. ARIMA(1,1,1)</h4>
                  <p style={{ fontSize: 12.5, color: '#64748b', marginTop: 6, lineHeight: 1.5 }}>
                    Models autoregression, non-stationary trend differencing, and shock recovery. Solved via Maximum Likelihood Estimation (MLE).
                  </p>
                </div>
                <div style={{ backgroundColor: '#ffffff', padding: 20, borderRadius: 10, border: '1px solid #e2e8f0' }}>
                  <h4 style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>3. Dynamic Safety Stock</h4>
                  <p style={{ fontSize: 12.5, color: '#64748b', marginTop: 6, lineHeight: 1.5 }}>
                    ROP = (Daily Demand &times; Lead Time) + (Daily Demand &times; 3). Automatically adjusts thresholds as seasonal demand changes.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ════════════════════ VIEW 4: SALES ORDERS ════════════════════ */}
          {activeTab === 'sales' && (
            <div style={{ maxWidth: 640, margin: '0 auto', backgroundColor: '#ffffff', borderRadius: 10, border: '1px solid #e2e8f0', padding: 28 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>Record Sales Transaction</h2>
              <p style={{ fontSize: 13, color: '#64748b', marginBottom: 20 }}>
                Executes an atomic transaction that inserts line items and invokes <code>fn_deduct_stock</code> with trigger protection.
              </p>

              <form onSubmit={handleSaleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Customer</label>
                  <select
                    required
                    value={saleForm.customer_id}
                    onChange={e => setSaleForm({ ...saleForm, customer_id: e.target.value })}
                    style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                  >
                    <option value="">Select Customer...</option>
                    {customers.map(c => (
                      <option key={c.customer_id} value={c.customer_id}>{c.customer_name} ({c.email})</option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Fulfilling Warehouse</label>
                    <select
                      required
                      value={saleForm.warehouse_id}
                      onChange={e => setSaleForm({ ...saleForm, warehouse_id: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                    >
                      <option value="">Select Warehouse...</option>
                      {warehouses.map(w => (
                        <option key={w.warehouse_id} value={w.warehouse_id}>{w.warehouse_name}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Payment Method</label>
                    <select
                      value={saleForm.payment_method}
                      onChange={e => setSaleForm({ ...saleForm, payment_method: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                    >
                      <option value="card">Credit / Debit Card</option>
                      <option value="upi">UPI / Instant</option>
                      <option value="cash">Cash on Delivery</option>
                      <option value="bank_transfer">Direct Bank Transfer</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Product</label>
                  <select
                    required
                    value={saleForm.product_id}
                    onChange={e => {
                      const p = products.find(prod => prod.product_id === Number(e.target.value));
                      setSaleForm({
                        ...saleForm,
                        product_id: e.target.value,
                        unit_price: p ? p.unit_price : 0,
                      });
                    }}
                    style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                  >
                    <option value="">Select Product...</option>
                    {products.map(p => (
                      <option key={p.product_id} value={p.product_id}>{p.sku} — {p.product_name} (₹{p.unit_price})</option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Quantity</label>
                    <input
                      type="number"
                      min="1"
                      required
                      value={saleForm.quantity}
                      onChange={e => setSaleForm({ ...saleForm, quantity: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Unit Price (₹)</label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      value={saleForm.unit_price}
                      onChange={e => setSaleForm({ ...saleForm, unit_price: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                    />
                  </div>
                </div>

                <div style={{ backgroundColor: '#f8fafc', padding: '14px 18px', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 13.5, color: '#64748b', fontWeight: 500 }}>Transaction Total</span>
                  <span style={{ fontSize: 20, fontWeight: 700, color: '#0f172a' }}>
                    ₹{(Number(saleForm.quantity || 0) * Number(saleForm.unit_price || 0) - Number(saleForm.discount || 0)).toFixed(2)}
                  </span>
                </div>

                <button
                  type="submit"
                  style={{
                    backgroundColor: '#2563eb',
                    color: '#ffffff',
                    border: 'none',
                    padding: '11px',
                    borderRadius: 6,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Confirm & Deduct Stock
                </button>
              </form>
            </div>
          )}

          {/* ════════════════════ VIEW 5: PURCHASE ORDERS ════════════════════ */}
          {activeTab === 'purchase_orders' && (
            <div style={{ maxWidth: 640, margin: '0 auto', backgroundColor: '#ffffff', borderRadius: 10, border: '1px solid #e2e8f0', padding: 28 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>Receive Inbound Purchase Order</h2>
              <p style={{ fontSize: 13, color: '#64748b', marginBottom: 20 }}>
                Restocks inventory via <code>fn_receive_stock</code> stored function, adjusting stock on hand.
              </p>

              <form onSubmit={handlePoSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Purchase Order</label>
                  <select
                    required
                    value={poForm.po_id}
                    onChange={e => setPoForm({ ...poForm, po_id: e.target.value })}
                    style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                  >
                    <option value="">Select Purchase Order...</option>
                    {purchaseOrders.map(po => (
                      <option key={po.po_id} value={po.po_id}>PO #{po.po_id} — {po.supplier_name} ({po.status})</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Receiving Warehouse</label>
                  <select
                    required
                    value={poForm.warehouse_id}
                    onChange={e => setPoForm({ ...poForm, warehouse_id: e.target.value })}
                    style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                  >
                    <option value="">Select Warehouse...</option>
                    {warehouses.map(w => (
                      <option key={w.warehouse_id} value={w.warehouse_id}>{w.warehouse_name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Product Received</label>
                  <select
                    required
                    value={poForm.product_id}
                    onChange={e => {
                      const p = products.find(prod => prod.product_id === Number(e.target.value));
                      setPoForm({
                        ...poForm,
                        product_id: e.target.value,
                        unit_cost: p ? (p.unit_price * 0.6).toFixed(2) : 0,
                      });
                    }}
                    style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                  >
                    <option value="">Select Product...</option>
                    {products.map(p => (
                      <option key={p.product_id} value={p.product_id}>{p.sku} — {p.product_name}</option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Quantity Received</label>
                    <input
                      type="number"
                      min="1"
                      required
                      value={poForm.quantity}
                      onChange={e => setPoForm({ ...poForm, quantity: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>Unit Cost (₹)</label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      value={poForm.unit_cost}
                      onChange={e => setPoForm({ ...poForm, unit_cost: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 13.5 }}
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  style={{
                    backgroundColor: '#16a34a',
                    color: '#ffffff',
                    border: 'none',
                    padding: '11px',
                    borderRadius: 6,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Receive Stock & Update Inventory
                </button>
              </form>
            </div>
          )}

          {/* ════════════════════ VIEW 6: REORDER ALERTS ════════════════════ */}
          {activeTab === 'alerts' && (
            <div style={{ backgroundColor: '#ffffff', borderRadius: 10, border: '1px solid #e2e8f0', padding: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                  <h2 style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>Automated Reorder Alerts</h2>
                  <p style={{ fontSize: 13, color: '#64748b' }}>Raised when available inventory drops below lead-time demand threshold</p>
                </div>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '2px solid #e2e8f0', textAlign: 'left', color: '#475569' }}>
                      <th style={{ padding: '10px 12px' }}>ID</th>
                      <th style={{ padding: '10px 12px' }}>Alert Date</th>
                      <th style={{ padding: '10px 12px' }}>SKU & Product</th>
                      <th style={{ padding: '10px 12px' }}>Warehouse</th>
                      <th style={{ padding: '10px 12px' }}>Supplier</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right' }}>Suggested Order</th>
                      <th style={{ padding: '10px 12px', textAlign: 'center' }}>Status</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.length === 0 ? (
                      <tr>
                        <td colSpan={8} style={{ padding: 28, textAlign: 'center', color: '#64748b' }}>
                          No active reorder alerts found. Run the forecasting pipeline to evaluate stock thresholds.
                        </td>
                      </tr>
                    ) : (
                      alerts.map(a => (
                        <tr key={a.alert_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: '12px', color: '#64748b' }}>#{a.alert_id}</td>
                          <td style={{ padding: '12px' }}>{a.alert_date}</td>
                          <td style={{ padding: '12px', fontWeight: 600 }}>{a.product_name} <span style={{ color: '#64748b', fontWeight: 400 }}>({a.sku})</span></td>
                          <td style={{ padding: '12px' }}>{a.warehouse_name}</td>
                          <td style={{ padding: '12px' }}>{a.supplier_name}</td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700, color: '#dc2626' }}>{a.suggested_order_qty} units</td>
                          <td style={{ padding: '12px', textAlign: 'center' }}>
                            <span style={{
                              fontSize: 11,
                              fontWeight: 700,
                              padding: '3px 10px',
                              borderRadius: 999,
                              backgroundColor: a.status === 'open' ? '#fee2e2' : a.status === 'acknowledged' ? '#fef3c7' : '#dcfce7',
                              color: a.status === 'open' ? '#991b1b' : a.status === 'acknowledged' ? '#92400e' : '#166534',
                            }}>
                              {a.status.toUpperCase()}
                            </span>
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            <div style={{ display: 'inline-flex', gap: 6 }}>
                              {a.status === 'open' && (
                                <button
                                  onClick={() => handleUpdateAlert(a.alert_id, 'acknowledged')}
                                  style={{ padding: '4px 8px', fontSize: 12, borderRadius: 4, border: '1px solid #cbd5e1', cursor: 'pointer', backgroundColor: '#fff' }}
                                >
                                  Acknowledge
                                </button>
                              )}
                              {a.status !== 'resolved' && (
                                <button
                                  onClick={() => handleUpdateAlert(a.alert_id, 'resolved')}
                                  style={{ padding: '4px 8px', fontSize: 12, borderRadius: 4, backgroundColor: '#16a34a', color: '#fff', border: 'none', cursor: 'pointer' }}
                                >
                                  Resolve
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
