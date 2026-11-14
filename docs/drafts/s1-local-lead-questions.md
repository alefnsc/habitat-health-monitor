# S1 draft: questions for the Local Lead (English and Portuguese)

For the operator to ask in person or by email. Nothing is sent by the agent. Record answers in `docs/decisions/local-lead.md` (English only, role only, no personal data about the Lead). Each question needs "Answer:" and "Asked at:"; a question still waiting is "Answer: pending (emailed HH:MM)".

Order: prior work and ground truth first (they gate the camera lane), then the live pitch, then branding.

Before asking: run `git ls-remote https://github.com/alefnsc/ground-truth HEAD` without credentials and record "ground-truth public: yes/no" with the time (HH:MM). If no, tell the Software lane at once (C10, C11, C12b, C12c stop).

## A. Prior work and ground truth

**Q3. Prior work.**
EN: Is declared prior work acceptable? Our entry uses an Apache-2.0 library called `ground-truth` (https://github.com/alefnsc/ground-truth), written 23 Sep to 11 Oct 2026, before the event. It will be public before we use it, is vendored at a pinned commit, and is listed in References. Is that allowed, and is there anything we must declare in the submission form?
PT: Trabalho anterior declarado é aceito? Nossa entrega usa uma biblioteca Apache-2.0 chamada `ground-truth` (https://github.com/alefnsc/ground-truth), escrita de 23/09 a 11/10/2026, antes do evento. Ela será pública antes do uso, fica fixada em um commit específico e consta nas Referências. Isso é permitido? Precisamos declarar algo a mais no formulário?

**Q4. Naming an open-source library.**
EN: Does citing an open-source library by its exact project name in References count as promoting a commercial product? Some library names contain a company name.
PT: Citar uma biblioteca de código aberto pelo nome exato do projeto nas Referências conta como promover um produto comercial? Alguns nomes de bibliotecas contêm o nome de uma empresa.

**Q6. Team members' own data.**
EN: May adult team members' own consented, pseudonymised readings (heart rate, SpO2, temperature) appear in the validation data we publish?
PT: Podemos publicar, nos dados de validação, leituras (frequência cardíaca, SpO2, temperatura) de membros adultos da equipe, com consentimento e pseudonimizadas?

## B. Live pitch and judging

**Q1. Live pitch.**
EN: Is there a live pitch or table judging? If so, how long is it, in which language, and may we show hardware in person?
PT: Haverá apresentação ao vivo ou avaliação presencial? Se sim, quanto tempo dura, em que idioma, e podemos mostrar hardware presencialmente?

**Q2. Local judging and nominations.**
EN: When do local judges review submissions, and how many Global Nominees can São Paulo send?
PT: Quando os jurados locais avaliam as entregas, e quantos Global Nominees São Paulo pode indicar?

## C. Branding

**Q5. Team name.**
EN: Can the team name be changed before submission? The current name contains a company name, which rule R9 on the site does not allow in our entry. We propose "Habitat Voyager".
PT: Podemos mudar o nome da equipe antes da submissão? O nome atual contém o nome de uma empresa, o que a regra R9 do site não permite na entrega. Propomos "Habitat Voyager".

## Fallback email (if the Lead is not reachable by 10:30 / 11:30)

Operator sends from their own account; suggested body in two languages:

EN: Hello, we are a São Paulo team in the Space Apps Challenge. Six short questions before we submit: (1) live pitch format; (2) local judging dates and Global Nominee slots; (3) whether declared open-source prior work is accepted; (4) whether citing an open-source library by name counts as promotion; (5) whether we can rename the team; (6) whether team members' own consented, pseudonymised readings may appear in validation data. Thank you.
PT: Olá, somos uma equipe de São Paulo no Space Apps Challenge. Seis perguntas rápidas antes da submissão: (1) formato da apresentação ao vivo; (2) datas da avaliação local e vagas de Global Nominees; (3) se trabalho anterior de código aberto, declarado, é aceito; (4) se citar uma biblioteca de código aberto pelo nome conta como promoção; (5) se podemos renomear a equipe; (6) se leituras de membros da equipe, com consentimento e pseudonimizadas, podem aparecer nos dados de validação. Obrigado.

## Recording template (for `docs/decisions/local-lead.md`, English)

ground-truth public: yes/no (checked HH:MM)
Q1 ... Q6: "Answer:" and "Asked at:" lines; "Answer: pending (emailed HH:MM)" if waiting.
If Q3 is "no" or ground-truth is not public: tell the Software lane at once; S10 runs on the load cell only.
