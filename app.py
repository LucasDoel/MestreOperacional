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

    # CSS to make the "table" look like a real table with borders
    st.markdown("""
        <style>
        [data-testid="column"] {
            border: 1px solid #e6e9ef;
            padding: 5px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            min-height: 50px;
        }
        .stExpander {
            border: 1px solid #e6e9ef;
            margin-top: -1px;
        }
        p {
            margin-bottom: 0px;
        }
        div.stTextInput > div > div > input {
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)

    # Column definitions
    cols_width = [1.5, 1.2, 1, 1, 1, 1, 1, 1, 1, 1]

    # Headers
    h_cols = st.columns(cols_width)
    headers = [
        "Nome", "Horário de chegada", "1° apontamento", "Dif. Chegada até 1° Ap",
        "Horário primeiro efetivo", "Tempo chegada até 1° Ef", "Tempo Apont. até 1° Ef",
        "Último efetivo", "Fim de turno", "Tempo Úl. Ef. até Fim"
    ]
    for col, header in zip(h_cols, headers):
        col.markdown(f"**{header}**")

    for op in operators:
        op_data = metrics_df[metrics_df['Nome'] == op]

        # Arrival time is per operator per day (simplification based on prompt "logo após a coluna com os nomes de operador")
        arrival_key = f"{date_str}_{op}"
        current_arrival = arrival_times.get(arrival_key, "")

        # If multiple machines, use an expander
        if len(op_data) > 1:
            row_cols = st.columns(cols_width)
            row_cols[0].write(op)
            new_arrival = row_cols[1].text_input("Chegada", value=current_arrival, key=arrival_key, label_visibility="collapsed")
            if new_arrival != current_arrival:
                arrival_times[arrival_key] = new_arrival
                save_arrival_times(arrival_times)
                st.rerun()

            # Show "Múltiplas Máquinas" in other columns or leave empty
            for i in range(2, len(row_cols)):
                row_cols[i].write("---")

            with st.expander(f"Expandir máquinas para {op}"):
                for idx, row in op_data.iterrows():
                    maquina = row['Máquina']

                    # Recalculate with arrival time
                    # We use the same arrival time for all machines of this operator
                    temp_dict = {f"{op}_{maquina}": new_arrival}
                    row_metrics = calculate_arrival_metrics(pd.DataFrame([row]), temp_dict).iloc[0]

                    m_cols = st.columns(cols_width)
                    m_cols[0].write(maquina)
                    m_cols[1].write("---") # Arrival input is above
                    m_cols[2].write(format_time(row_metrics['1° apontamento']))
                    m_cols[3].write(format_timedelta(row_metrics['Diferença chegada até 1° apontamento']))
                    m_cols[4].write(format_time(row_metrics['Horário primeiro efetivo']))
                    m_cols[5].write(format_timedelta(row_metrics['tempo de chegada até o primeiro efetivo']))
                    m_cols[6].write(format_timedelta(row_metrics['Tempo de apontamento até o primeiro efetivo']))
                    m_cols[7].write(format_time(row_metrics['ultimo efetivo']))
                    m_cols[8].write(format_time(row_metrics['Fim de turno']))
                    m_cols[9].write(format_timedelta(row_metrics['Tempo ultimo efetivo fim de turno']))
        else:
            # Single machine
            row = op_data.iloc[0]
            maquina = row['Máquina']
            row_cols = st.columns(cols_width)
            row_cols[0].write(f"{op} ({maquina})")

            new_arrival = row_cols[1].text_input("Chegada", value=current_arrival, key=arrival_key, label_visibility="collapsed")
            if new_arrival != current_arrival:
                arrival_times[arrival_key] = new_arrival
                save_arrival_times(arrival_times)
                st.rerun()

            temp_dict = {f"{op}_{maquina}": new_arrival}
            row_metrics = calculate_arrival_metrics(pd.DataFrame([row]), temp_dict).iloc[0]

            row_cols[2].write(format_time(row_metrics['1° apontamento']))
            row_cols[3].write(format_timedelta(row_metrics['Diferença chegada até 1° apontamento']))
            row_cols[4].write(format_time(row_metrics['Horário primeiro efetivo']))
            row_cols[5].write(format_timedelta(row_metrics['tempo de chegada até o primeiro efetivo']))
            row_cols[6].write(format_timedelta(row_metrics['Tempo de apontamento até o primeiro efetivo']))
            row_cols[7].write(format_time(row_metrics['ultimo efetivo']))
            row_cols[8].write(format_time(row_metrics['Fim de turno']))
            row_cols[9].write(format_timedelta(row_metrics['Tempo ultimo efetivo fim de turno']))
