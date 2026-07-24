# Framework de transformação Vago → Goal

## 1. Objetivo operacional

O framework não tenta “embelezar” uma solicitação. Ele transforma intenção em um contrato de execução que outra LLM consegue cumprir e que uma pessoa consegue revisar.

O processo é composto por cinco estágios:

1. **Extract:** identifica objetivo, audiência, artefato, contexto e limites já presentes.
2. **Normalize:** reescreve o sucesso como estado final observável e separa fatos de hipóteses.
3. **Enrich:** infere casos de borda, riscos, não objetivos e critérios de aceite proporcionais.
4. **Adapt:** escolhe a estrutura do prompt conforme o destino, sem mudar o significado do contrato.
5. **Validate:** procura lacunas, contradições, fontes inválidas e critérios não verificáveis antes de renderizar.

## 2. GoalSpec como fonte de verdade

O `GoalSpec` é a representação canônica. Templates são apenas visualizações desse contrato.

| Campo | Pergunta respondida | Regra |
| --- | --- | --- |
| `role` | Qual competência muda a qualidade da execução? | Seja específico; evite biografias e superlativos vazios. |
| `goal` | Como o estado final será reconhecido? | Comece pelo resultado; processo só quando for requisito. |
| `success_criteria` | O que precisa ser verdade no final? | Cada item deve ser testável ou inspecionável. |
| `context` | Que fatos mudam a solução? | Não replique conhecimento irrelevante. |
| `inputs` | Em que artefatos o executor opera? | Identifique tipo, origem e semântica quando conhecidos. |
| `references` | Quais são as fontes de verdade externas? | Somente URLs absolutas e não inventadas. |
| `constraints` | Que limites previnem falhas reais? | Inclua segurança, compatibilidade, performance e escopo apenas se aplicáveis. |
| `non_goals` | O que está explicitamente fora de escopo? | Use para conter expansão lateral. |
| `edge_cases` | O que tende a quebrar? | Cubra erros, vazio/nulo, limites, concorrência, segurança e recuperação conforme o domínio. |
| `output_contract` | Como o resultado deve ser consumido? | Defina formato, seções, verbosidade e explicações. |
| `assumptions` | O que foi inferido de forma reversível? | Declare; não disfarce como fato. |
| `blocking_questions` | O que impede execução responsável? | Reserve para escolhas materiais, irreversíveis ou de alto risco. |
| `validation_checks` | Como o executor se autocorrige? | Verifique critérios, limites, fontes e formato antes de concluir. |

## 3. Política de inferência

O metaprompter deve fazer progresso com informação parcial sem fabricar precisão.

1. Preserve fatos explícitos.
2. Para uma lacuna de baixo risco e reversível, escolha a hipótese convencional e registre-a em `assumptions`.
3. Para uma lacuna que altera materialmente arquitetura, custo, segurança, dados ou ação externa, registre uma pergunta em `blocking_questions`.
4. Se uma URL ou caminho não foi fornecido, use um marcador de lacuna descritivo; nunca invente um endereço plausível.
5. Não adicione requisitos de performance, bibliotecas proibidas ou tecnologias específicas sem evidência no pedido ou no contexto.

## 4. Inferência de casos de borda

Use uma seleção proporcional, não uma checklist infinita:

- **API/autenticação:** credencial inválida, bloqueio, expiração, rate limit, timeout, indisponibilidade, replay e vazamento de segredo.
- **Dados:** vazio, nulo, duplicado, formato inválido, encoding, volume extremo e migração parcial.
- **UI:** carregamento, erro, vazio, responsividade, teclado, leitor de tela e reentrada.
- **Concorrência:** repetição, corrida, idempotência, retry e escrita parcial.
- **Arquivos:** inexistente, permissão, path traversal, arquivo grande, conflito e escrita atômica.
- **Análise:** definição ambígua, denominador incorreto, período incompleto, outlier e fonte divergente.

Cada caso incluído precisa se converter em tratamento, teste, mensagem ou limitação explícita.

## 5. Perfis de destino

### Claude Code

- Use tags XML consistentes para distinguir dados de instruções.
- Coloque documentos longos antes da tarefa e preserve metadados de origem.
- Defina política de ferramentas e limites de ação de forma explícita.
- Solicite análise e planejamento internos; peça na resposta somente decisões, evidências e resultado.

### Codex

- Comece pelo resultado desejado.
- Nomeie arquivos, diretórios e URLs completos quando disponíveis.
- Delimite escopo, contratos de entrada/saída e alterações que devem permanecer intactas.
- Instrua o agente a inspecionar convenções do workspace, preservar mudanças alheias e verificar o trabalho.
- Prefira um handoff curto: resultado, arquivos modificados, testes e limitações.

### Cursor

- Mantenha o prompt da tarefa compacto; regras duráveis pertencem às regras do projeto.
- Declare arquivos em escopo, contratos e convenções relevantes.
- Peça mudanças pequenas e verificáveis, coerentes com o código ao redor.
- Separe instrução temporária de política persistente do repositório.

### Gemini

- Use hierarquia Markdown consistente ou XML, mas não misture estruturas sem necessidade.
- Unifique contexto longo e identifique claramente cada modalidade ou documento.
- Coloque limites críticos no início; em contexto extenso, deixe a tarefa específica depois dos dados.
- Use exemplos poucos e consistentes quando o formato for difícil de descrever.
- Para JSON complexo, prefira schema/structured output nativo em vez de confiar apenas em instruções textuais.

## 6. Autocrítica sem exposição de chain-of-thought

O prompt final não deve pedir uma transcrição do raciocínio privado. Ele exige um ciclo interno de qualidade:

1. planejar silenciosamente;
2. executar;
3. comparar o resultado com `success_criteria` e `constraints`;
4. corrigir violações encontradas;
5. reportar apenas o resultado, evidências verificáveis, decisões relevantes e limitações.

## 7. Quality gates

Um `GoalSpec` só está pronto quando:

- os cinco pilares estão preenchidos;
- o objetivo descreve um resultado único e acionável;
- existe pelo menos um critério de sucesso, uma restrição, um caso de borda e uma verificação final;
- todas as referências são URLs absolutas;
- casos de borda têm relação com o domínio;
- hipóteses não aparecem como fatos;
- perguntas bloqueantes são realmente materiais;
- formato de saída é explícito;
- não há conflito entre objetivo, limites e formato.

O validador local cobre regras estruturais e URLs. Contradições semânticas continuam sendo responsabilidade da etapa metaprompter e de avaliações de domínio.

## 8. Evolução e avaliação

Prompts devem ser tratados como código:

- versione `GoalSpec`, templates e casos de teste;
- mantenha um conjunto de solicitações reais com saídas aprovadas;
- avalie completude, aderência, custo, latência e taxa de retrabalho separadamente;
- altere uma dimensão por vez;
- promova um template apenas quando ele melhora critérios mensuráveis no conjunto de avaliação.
