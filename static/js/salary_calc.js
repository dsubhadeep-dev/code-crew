function calcSalary() {
  const num = (id) => parseFloat(document.getElementById(id).value) || 0;
  const money = (v) => '₹' + v.toFixed(2);

  const wage = num('wage');
  const basicPct = num('basic_pct');
  const hraPct = num('hra_pct');
  const standardAllowance = num('standard_allowance');
  const bonusPct = num('performance_bonus_pct');
  const ltaPct = num('lta_pct');
  const tax = num('professional_tax');
  const pfEmpPct = num('pf_employee_pct');
  const pfErPct = num('pf_employer_pct');

  const basic = wage * (basicPct / 100);
  const hra = basic * (hraPct / 100);
  const bonus = basic * (bonusPct / 100);
  const lta = basic * (ltaPct / 100);
  const pfEmp = basic * (pfEmpPct / 100);
  const pfEr = basic * (pfErPct / 100);

  const sumOthers = basic + hra + standardAllowance + bonus + lta;
  const fixedAllowance = Math.max(wage - sumOthers, 0);
  const componentsTotal = sumOthers + fixedAllowance;

  document.getElementById('out_basic').textContent = money(basic);
  document.getElementById('out_hra').textContent = money(hra);
  document.getElementById('out_std').textContent = money(standardAllowance);
  document.getElementById('out_bonus').textContent = money(bonus);
  document.getElementById('out_lta').textContent = money(lta);
  document.getElementById('out_fixed').textContent = money(fixedAllowance);
  document.getElementById('out_tax').textContent = '- ' + money(tax);
  document.getElementById('out_pf_emp').textContent = '- ' + money(pfEmp);
  document.getElementById('out_pf_emp2').textContent = money(pfEr);
  document.getElementById('out_total').textContent = money(componentsTotal) + ' / ' + money(wage);

  const warn = document.getElementById('out_warn');
  warn.style.display = sumOthers > wage ? 'block' : 'none';
}

document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('salaryForm');
  if (!form) return;
  form.querySelectorAll('input[type="number"]').forEach((input) => {
    input.addEventListener('input', calcSalary);
  });
  calcSalary();
});s