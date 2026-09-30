# Agregador de Pesquisas Eleitorais - Presidencial Brasil 2026

Um agregador estatístico e probabilístico independente para as eleições presidenciais brasileiras de 2026, inspirado em iniciativas como o Plano Político, FiveThirtyEight e Silver Bulletin.

O sistema coleta pesquisas eleitorais publicadas em fontes primárias e veículos jornalísticos, valida os registros junto às regras do Tribunal Superior Eleitoral (TSE - PesqEle), calcula médias diárias móveis ponderadas com intervalos de confiança via bootstrap não-paramétrico e gera visualizações interativas em um front-end estático.

---

## 📁 Estrutura do Projeto

```
.
├── coleta/                          # Módulos de coleta e scraping por fonte (1 arquivo por veículo)
│   ├── __init__.py
│   ├── base.py                      # Classe base com respeito a robots.txt e rate limiting
│   ├── g1.py                        # Coletor G1 (Globo)
│   ├── folha.py                     # Coletor Folha de S.Paulo
│   ├── estadao.py                   # Coletor Estadão
│   ├── uol.py                       # Coletor UOL Notícias
│   └── cnn_brasil.py                # Coletor CNN Brasil
├── modelo/                          # Modelo estatístico, agregação e persistência
│   ├── __init__.py
│   ├── config.py                    # Leitura tipada do config.yaml
│   ├── database.py                  # Conexão, DDL e operações CRUD com SQLite
│   ├── validador.py                 # Validação de regras do TSE, datas, amostras e percentuais
│   └── importar_csv.py              # Ingestão de pesquisas com auditoria e quarentena
├── dados/                           # Banco SQLite, esquemas e dados gerados
│   ├── schema.sql                   # Esquema DDL para SQLite (com views analíticas)
│   ├── schema_postgres.sql          # Versão adaptada para migração direta para PostgreSQL
│   ├── quarentena.csv               # Registros descartados ou pendentes de auditoria
│   └── exemplos/
│       └── pesquisas_ficticias_2026.csv # Dados 100% fictícios para testes e simulação
├── site/                            # Front-end estático (HTML, CSS e JS puro)
│   └── index.html
├── tests/                           # Bateria de testes unitários e de integração (pytest)
│   ├── test_validador.py            # Testes das regras de validação
│   ├── test_database.py             # Testes do banco SQLite e views
│   └── test_etapa1_estrutura.py     # Testes de conformidade da estrutura do projeto
├── config.yaml                      # Central de parametrização do modelo e da coleta
├── run_pipeline.py                  # Script principal para cron / CI/CD
├── requirements.txt                 # Dependências do projeto Python
└── README.md                        # Documentação do projeto
```

---

## 🗄️ Modelo de Dados

O banco de dados foi projetado no SQLite com integridade referencial ativa (`PRAGMA foreign_keys = ON;`) e mapeamento direto para PostgreSQL.

### Entidades

- **`instituto`**: Cadastro de institutos (`nome`, `peso`, `vies_historico`).
- **`pesquisa`**: Metadados do registro no TSE (`registro_tse` único para deduplicação, `instituto_id`, `data_inicio`, `data_fim`, `amostra`, `margem_erro`, `metodologia`, flag `impugnada`).
- **`cenario`**: Cenários de votação de uma pesquisa (`turno` 1 ou 2, `cenario` como "Estimulada 1", "Espontânea", "2º Turno"). Permite que uma mesma pesquisa TSE contenha múltiplos cenários sem duplicar metadados.
- **`resultado`**: Votos por opção (`candidato`, `percentual`), incluindo votos nominais, `Branco/Nulo` e `Indeciso/Não Sabe`.
- **`fonte`**: Rastreabilidade de URLs coletadas (`pesquisa_id`, `portal`, `url`, `data_coleta`).
- **`quarentena`**: Registro de tentativas de inserção que violaram regras de integridade para revisão manual.

### Views Analíticas
- `vw_pesquisas_completas`: visão relacional consolidada para consumo do modelo de agregação.
- `vw_cenarios_pesquisa`: consolidação por cenário com contagem de candidatos e soma de percentuais.

---

## ⚙️ Configuração (`config.yaml`)

Todos os parâmetros do modelo e do pipeline são customizáveis sem alterar código:

```yaml
modelo:
  meia_vida_dias: 14.0             # Meia-vida do decaimento exponencial temporal
  data_inicio_serie: "2026-01-01"  # Data inicial da série histórica
  n_bootstraps: 2000               # Reamostragens do bootstrap
  intervalo_confianca:
    percentil_inferior: 2.5
    percentil_superior: 97.5
  peso_amostra_habilitado: true    # Peso proporcional à raiz da amostra (sqrt(N))
  house_effects:
    habilitado: true
    min_pesquisas_instituto: 5     # Mínimo de pesquisas para calcular viés
```

---

## 🚀 Instalação e Execução

### 1. Pré-requisitos
- Python 3.11+ instalado.

### 2. Instalação das dependências
```bash
python -m pip install -r requirements.txt
```

### 3. Inicializar o banco e importar dados fictícios de exemplo
```bash
python run_pipeline.py --init-db --import-exemplo
```

### 4. Execução dos testes
```bash
pytest -v
```

---

## 🛡️ Regras de Validação e Quarentena

Para evitar que pesquisas fraudulentas, com erros de digitação ou suspensas entrem no cálculo estatístico:
1. **Registro TSE Obrigatório**: Máscara `^[A-Z]{2}-\d{5}/\d{4}$` (ex: `BR-00001/2026`).
2. **Amostra Válida**: Valor inteiro positivo $\ge 100$.
3. **Consistência de Datas**: `data_fim >= data_inicio`. A data de referência para decaimento temporal é sempre `data_fim` (conclusão do campo).
4. **Soma dos Percentuais**: A soma de um cenário deve estar entre **90% e 105%** (permitindo pequenas margens de arredondamento jornalístico).
5. **Pesquisas Impugnadas**: Se marcadas com `impugnada = 1`, são mantidas no banco para fins históricos, mas excluídas do modelo de cálculo.
6. **Quarentena**: Qualquer registro que falhar é arquivado na tabela `quarentena` e em `dados/quarentena.csv` para auditoria manual.

---

## ⚠️ Limitações do Modelo

1. **Agregador não é bola de cristal**: O modelo reflete a intenção de voto no momento em que as pesquisas foram a campo, não sendo uma previsão determinística da data da eleição.
2. **Dependência de Transparência**: O modelo depende da qualidade das metodologias e da regularidade de divulgação dos institutos.
3. **Efeito Casa (House Effects)**: Requer uma densidade mínima de pesquisas (padrão: 5 por instituto) na mesma janela temporal para estimar com precisão desvios sistemáticos.
4. **Fictício vs Real**: Durante o desenvolvimento das Etapas 1 a 3, os dados de demonstração são **100% fictícios** e estão explicitamente marcados como tal na coluna `dado_ficticio = 'SIMULADO'`.

---

## 📅 Roteiro de Entregas

- [x] **Etapa 1:** Estrutura do projeto, esquema do banco SQLite/Postgres, `config.yaml`, validação, quarentena e CSV de dados fictícios.
- [ ] **Etapa 2:** Modelo de agregação matemática (pesos temporais, raiz da amostra, house effects, média diária, bootstrap de 2.000 iterações e votos válidos).
- [ ] **Etapa 3:** Front-end estático responsivo com gráficos interativos e tabela de pesquisas.
- [ ] **Etapa 4:** Coletores reais de portais com extração estruturada e validação TSE.
- [ ] **Etapa 5:** Automação diária com `run_pipeline.py` e rotinas de deploy.
- [ ] **Etapa 6 (Opcional):** Modelo multinível e agregação por UF.
