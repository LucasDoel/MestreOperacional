import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, time, timedelta

# Set page config
st.set_page_config(page_title="Linha do Tempo de Operadores", layout="wide")

@st.cache_data
def load_data(file_path):
    df = pd.read_excel(file_path)
    return df

DATA_FILE = "Linha do tempo.xlsx"

if not os.path.exists(DATA_FILE):
    st.error(f"Arquivo {DATA_FILE} não encontrado.")
    st.stop()

df_raw = load_data(DATA_FILE)

def preprocess_data(df):
    df = df.copy()

    # Normalize string columns
    string_cols = ['Nome', 'Descrição da Operação', 'Descrição do Grupo da Operação', 'Descrição do Equipamento']
    for col in string_cols:
        df[col] = df[col].astype(str).str.strip().str.upper()

    # Convert 'Data Hora Local' to date objects
    df['Data'] = pd.to_datetime(df['Data Hora Local'], format='%d/%m/%Y').dt.date

    # Convert 'Hora Inicial' and 'Hora Final' to time objects and then to datetime for easier calculation
    # We use a dummy date to allow subtraction
    dummy_date = datetime(2000, 1, 1)

    def to_datetime(time_str):
        try:
            if pd.isna(time_str) or time_str == 'nan':
                return None
            t = datetime.strptime(str(time_str), '%H:%M:%S').time()
            return datetime.combine(dummy_date, t)
        except Exception:
            return None

    df['Hora Inicial DT'] = df['Hora Inicial'].apply(to_datetime)
    df['Hora Final DT'] = df['Hora Final'].apply(to_datetime)

    return df

df = preprocess_data(df_raw)

# Sidebar
st.sidebar.title("Filtros")
available_dates = sorted(df['Data'].unique())
selected_date = st.sidebar.date_input("Selecione a Data", value=available_dates[0] if available_dates else datetime.now().date(), min_value=min(available_dates) if available_dates else None, max_value=max(available_dates) if available_dates else None)

# Filter data
df_filtered = df[df['Data'] == selected_date]

def get_operator_metrics(df_filtered):
    # Group by Operator and Machine
    groups = df_filtered.groupby(['Nome', 'Descrição do Equipamento'])

    results = []
    for (nome, maquina), group in groups:
        group = group.sort_values('Hora Inicial DT')

        # 1° apontamento
        pa_mask = group['Descrição da Operação'] != 'FINAL DE EXPEDIENTE'
        primeiro_apontamento = group.loc[pa_mask, 'Hora Inicial DT'].min() if pa_mask.any() else None

        # Horário primeiro efetivo
        pe_mask = group['Descrição do Grupo da Operação'] == 'PRODUTIVA'
        primeiro_efetivo = group.loc[pe_mask, 'Hora Inicial DT'].min() if pe_mask.any() else None

        # ultimo efetivo
        ultimo_efetivo = group.loc[pe_mask, 'Hora Final DT'].max() if pe_mask.any() else None

        # Fim de turno
        fim_turno = group.loc[pa_mask, 'Hora Final DT'].max() if pa_mask.any() else None

        results.append({
            'Nome': nome,
            'Máquina': maquina,
            '1° apontamento': primeiro_apontamento,
            'Horário primeiro efetivo': primeiro_efetivo,
            'ultimo efetivo': ultimo_efetivo,
            'Fim de turno': fim_turno
        })

    df_res = pd.DataFrame(results)

    if not df_res.empty:
        # Tempo de apontamento até o primeiro efetivo
        df_res['Tempo de apontamento até o primeiro efetivo'] = df_res['Horário primeiro efetivo'] - df_res['1° apontamento']

        # Tempo ultimo efetivo fim de turno
        df_res['Tempo ultimo efetivo fim de turno'] = df_res['Fim de turno'] - df_res['ultimo efetivo']

    return df_res

def calculate_arrival_metrics(df_metrics, arrival_times_dict):
    df_res = df_metrics.copy()

    dummy_date = datetime(2000, 1, 1)

    def get_arrival_dt(row):
        key = f"{row['Nome']}_{row['Máquina']}"
        arrival_str = arrival_times_dict.get(key, "")
        if arrival_str:
            try:
                t = datetime.strptime(arrival_str, '%H:%M:%S').time()
                return datetime.combine(dummy_date, t)
            except:
                pass
        return None

    df_res['Horário de chegada DT'] = df_res.apply(get_arrival_dt, axis=1)

    # Diferença da coluna "Horário de chegada" até "1° apontamento"
    df_res['Diferença chegada até 1° apontamento'] = df_res.apply(
        lambda r: r['1° apontamento'] - r['Horário de chegada DT'] if pd.notna(r['1° apontamento']) and pd.notna(r['Horário de chegada DT']) else None,
        axis=1
    )

    # tempo de chegada até o primeiro efetivo
    df_res['tempo de chegada até o primeiro efetivo'] = df_res.apply(
        lambda r: r['Horário primeiro efetivo'] - r['Horário de chegada DT'] if pd.notna(r['Horário primeiro efetivo']) and pd.notna(r['Horário de chegada DT']) else None,
        axis=1
    )

    return df_res

def format_timedelta(td):
    if pd.isna(td):
        return ""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def format_time(dt):
    if pd.isna(dt) or dt is None:
        return ""
    return dt.strftime('%H:%M:%S')

PERSISTENCE_FILE = "chegadas.json"

def load_arrival_times():
    if os.path.exists(PERSISTENCE_FILE):
        with open(PERSISTENCE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_arrival_times(arrival_times):
    with open(PERSISTENCE_FILE, 'w') as f:
        json.dump(arrival_times, f)

# Main App Logic
st.title("Linha do Tempo de Operadores")

# Load and calculate metrics
arrival_times = load_arrival_times()
metrics_df = get_operator_metrics(df_filtered)

if metrics_df.empty:
    st.info("Nenhum dado encontrado para a data selecionada.")
else:
    date_str = selected_date.strftime('%Y-%m-%d')
    operators = sorted(metrics_df['Nome'].unique())

    # CSS for a modern, pleasant table-like interface
    st.markdown("""
        <style>
        .custom-header {
            background-color: #f0f2f6;
            border: 1px solid #e6e9ef;
            padding: 10px;
            font-weight: bold;
            text-align: center;
            font-size: 0.8rem;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 70px;
        }
        .custom-cell {
            border-right: 1px solid #e6e9ef;
            padding: 10px;
            text-align: center;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 60px;
        }
        .stContainer {
            border: 1px solid #e6e9ef;
            border-radius: 5px;
            margin-bottom: 10px;
            padding: 0px !important;
        }
        .stExpander {
            border: none !important;
            box-shadow: none !important;
        }
        p {
            margin-bottom: 0px;
            font-size: 0.9rem;
        }
        div.stTextInput > div > div > input {
            text-align: center;
            border-radius: 5px;
        }
        </style>
    """, unsafe_allow_html=True)

    # Column definitions
    cols_width = [1.5, 1.2, 1, 1, 1, 1, 1, 1, 1, 1]

    # Headers with Icons
    h_cols = st.columns(cols_width)
    headers = [
        "👤 Operador", "🕒 Chegada", "📝 1° Apont.", "⏱️ Dif. Ch. -> 1° Ap",
        "✅ 1° Efetivo", "⏱️ Ch. -> 1° Ef", "⏱️ Ap. -> 1° Ef",
        "🏁 Úl. Efetivo", "🚪 Fim Turno", "⏱️ Úl. Ef. -> Fim"
    ]
    for col, header in zip(h_cols, headers):
        col.markdown(f'<div class="custom-header">{header}</div>', unsafe_allow_html=True)

    for op in operators:
        op_data = metrics_df[metrics_df['Nome'] == op]
        arrival_key = f"{date_str}_{op}"
        current_arrival = arrival_times.get(arrival_key, "")

        with st.container(border=True):
            # If multiple machines, use an expander
            if len(op_data) > 1:
                row_cols = st.columns(cols_width)
                row_cols[0].markdown(f'<div class="custom-cell"><b>{op}</b></div>', unsafe_allow_html=True)

                with row_cols[1]:
                    new_arrival = st.text_input("Chegada", value=current_arrival, key=arrival_key, label_visibility="collapsed")
                    if new_arrival != current_arrival:
                        arrival_times[arrival_key] = new_arrival
                        save_arrival_times(arrival_times)
                        st.rerun()

                # Placeholders for summary/multiple machines
                for i in range(2, len(row_cols)):
                    row_cols[i].markdown('<div class="custom-cell">---</div>', unsafe_allow_html=True)

                with st.expander(f"Ver {len(op_data)} máquinas de {op}"):
                    for idx, row in op_data.iterrows():
                        maquina = row['Máquina']
                        temp_dict = {f"{op}_{maquina}": new_arrival}
                        row_metrics = calculate_arrival_metrics(pd.DataFrame([row]), temp_dict).iloc[0]

                        m_cols = st.columns(cols_width)
                        m_cols[0].markdown(f'<div class="custom-cell" style="font-size:0.8rem">{maquina}</div>', unsafe_allow_html=True)
                        m_cols[1].markdown('<div class="custom-cell">---</div>', unsafe_allow_html=True)
                        m_cols[2].markdown(f'<div class="custom-cell">{format_time(row_metrics["1° apontamento"])}</div>', unsafe_allow_html=True)
                        m_cols[3].markdown(f'<div class="custom-cell">{format_timedelta(row_metrics["Diferença chegada até 1° apontamento"])}</div>', unsafe_allow_html=True)
                        m_cols[4].markdown(f'<div class="custom-cell">{format_time(row_metrics["Horário primeiro efetivo"])}</div>', unsafe_allow_html=True)
                        m_cols[5].markdown(f'<div class="custom-cell">{format_timedelta(row_metrics["tempo de chegada até o primeiro efetivo"])}</div>', unsafe_allow_html=True)
                        m_cols[6].markdown(f'<div class="custom-cell">{format_timedelta(row_metrics["Tempo de apontamento até o primeiro efetivo"])}</div>', unsafe_allow_html=True)
                        m_cols[7].markdown(f'<div class="custom-cell">{format_time(row_metrics["ultimo efetivo"])}</div>', unsafe_allow_html=True)
                        m_cols[8].markdown(f'<div class="custom-cell">{format_time(row_metrics["Fim de turno"])}</div>', unsafe_allow_html=True)
                        m_cols[9].markdown(f'<div class="custom-cell">{format_timedelta(row_metrics["Tempo ultimo efetivo fim de turno"])}</div>', unsafe_allow_html=True)
            else:
                # Single machine
                row = op_data.iloc[0]
                maquina = row['Máquina']
                row_cols = st.columns(cols_width)
                row_cols[0].markdown(f'<div class="custom-cell"><b>{op}</b><br><small>({maquina})</small></div>', unsafe_allow_html=True)

                with row_cols[1]:
                    new_arrival = st.text_input("Chegada", value=current_arrival, key=arrival_key, label_visibility="collapsed")
                    if new_arrival != current_arrival:
                        arrival_times[arrival_key] = new_arrival
                        save_arrival_times(arrival_times)
                        st.rerun()

                temp_dict = {f"{op}_{maquina}": new_arrival}
                row_metrics = calculate_arrival_metrics(pd.DataFrame([row]), temp_dict).iloc[0]

                row_cols[2].markdown(f'<div class="custom-cell">{format_time(row_metrics["1° apontamento"])}</div>', unsafe_allow_html=True)
                row_cols[3].markdown(f'<div class="custom-cell">{format_timedelta(row_metrics["Diferença chegada até 1° apontamento"])}</div>', unsafe_allow_html=True)
                row_cols[4].markdown(f'<div class="custom-cell">{format_time(row_metrics["Horário primeiro efetivo"])}</div>', unsafe_allow_html=True)
                row_cols[5].markdown(f'<div class="custom-cell">{format_timedelta(row_metrics["tempo de chegada até o primeiro efetivo"])}</div>', unsafe_allow_html=True)
                row_cols[6].markdown(f'<div class="custom-cell">{format_timedelta(row_metrics["Tempo de apontamento até o primeiro efetivo"])}</div>', unsafe_allow_html=True)
                row_cols[7].markdown(f'<div class="custom-cell">{format_time(row_metrics["ultimo efetivo"])}</div>', unsafe_allow_html=True)
                row_cols[8].markdown(f'<div class="custom-cell">{format_time(row_metrics["Fim de turno"])}</div>', unsafe_allow_html=True)
                row_cols[9].markdown(f'<div class="custom-cell">{format_timedelta(row_metrics["Tempo ultimo efetivo fim de turno"])}</div>', unsafe_allow_html=True)
